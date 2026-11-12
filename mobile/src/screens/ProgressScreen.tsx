// 3·4단계: 서버가 수집·변환하는 동안 진행 상황을 보여주는 화면
import React, { useEffect, useRef, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Api, ApiError, JobStatus } from '../api';
import { Bar, Btn, C, Card, Note, StepBadge } from '../ui';

// 단계별로 전체 막대에서 차지하는 구간 (수집이 오래 걸리므로 가장 넓게)
const RANGE: Record<string, [number, number]> = {
  queued: [0, 0],
  toc: [0, 0.03],
  crawl: [0.03, 0.55],
  render: [0.55, 0.9],
  merge: [0.9, 1],
  done: [1, 1],
};

export function overall(j: JobStatus): number {
  const [a, b] = RANGE[j.phase] ?? [0, 0];
  const frac = j.total > 0 ? Math.min(1, j.done / j.total) : 0;
  return a + (b - a) * frac;
}

export function ProgressScreen({
  api,
  jobId,
  onDone,
  onLeave,
  onReset,
}: {
  api: Api;
  jobId: string;
  onDone: (j: JobStatus) => void;
  onLeave: () => void;
  onReset: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [job, setJob] = useState<JobStatus | null>(null);
  const [warn, setWarn] = useState('');
  const [lost, setLost] = useState(false);
  const fails = useRef(0);

  useEffect(() => {
    let alive = true;
    let busy = false;
    const tick = async () => {
      if (busy) return; // 앞선 요청이 안 끝났으면 겹쳐 보내지 않음
      busy = true;
      try {
        const j = await api.getJob(jobId);
        if (!alive) return;
        fails.current = 0;
        setWarn('');
        setJob(j);
        if (j.status === 'done') onDone(j);
      } catch (e: any) {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) {
          setLost(true);
        } else if (++fails.current >= 3) {
          setWarn('서버 응답을 기다리는 중입니다. 서버는 계속 작업 중이니 잠시만 기다려 주세요.');
        }
      } finally {
        busy = false;
      }
    };
    tick();
    const t = setInterval(tick, 1500);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [api, jobId, onDone]);

  const finished = job && (job.status === 'error' || job.status === 'cancelled');
  const pct = job ? overall(job) : 0;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: C.bg }}
      contentContainerStyle={{ padding: 16, paddingTop: insets.top + 12, paddingBottom: insets.bottom + 40 }}
    >
      <Card>
        <StepBadge n="3·4" title="서버에서 수집·변환 중" />
        {lost ? (
          <>
            <Note
              tone="err"
              text="서버가 이 작업을 기억하지 못합니다. (무료 서버가 다시 시작되면 작업이 사라져요.) 처음부터 다시 시작해 주세요."
            />
            <Btn title="설정으로 돌아가기" onPress={onReset} />
          </>
        ) : !job ? (
          <Note text="서버에 연결하는 중… (잠든 서버는 깨우는 데 1분쯤 걸려요)" />
        ) : (
          <>
            {job.book_title ? <Text style={{ color: C.ink, fontWeight: '700', fontSize: 16, marginBottom: 8 }}>{job.book_title}</Text> : null}
            <Text style={{ color: C.primary, fontWeight: '800', fontSize: 18, marginBottom: 8 }}>
              {finished ? (job.status === 'error' ? '오류로 멈췄습니다' : '취소되었습니다') : job.phase_label}
            </Text>
            <Bar value={finished ? pct : pct} />
            <Text style={{ color: C.ink, marginTop: 8, fontSize: 15 }}>
              {Math.round(pct * 100)}%{job.total ? `  ·  ${job.done} / ${job.total}` : ''}
            </Text>
            {job.status !== 'error' && job.status !== 'cancelled' ? (
              <Text style={{ color: C.sub, marginTop: 4 }} numberOfLines={2}>
                {job.message}
              </Text>
            ) : null}
          </>
        )}
      </Card>

      {warn ? <Card tone="warn"><Note text={warn} tone="warn" /></Card> : null}

      {job && job.failed_count > 0 && !finished ? (
        <Card tone="warn">
          <Note tone="warn" text={`불러오지 못한 페이지 ${job.failed_count}개 (PDF 에는 안내 문구로 들어갑니다)`} />
        </Card>
      ) : null}

      {job && finished ? (
        <Card tone="err">
          <Text style={{ color: C.err, fontWeight: '700', marginBottom: 6 }}>이유</Text>
          <Note tone="err" text={job.message} />
          <Btn title="설정으로 돌아가기" onPress={onReset} />
        </Card>
      ) : null}

      {job && job.logs.length ? (
        <Card>
          <Text style={{ color: C.sub, fontWeight: '700', marginBottom: 6 }}>최근 기록</Text>
          {job.logs.slice(-6).map((l, i) => (
            <Text key={i} style={{ color: C.ink, fontSize: 12, lineHeight: 18 }}>
              {l}
            </Text>
          ))}
        </Card>
      ) : null}

      {job && !finished && !lost ? (
        <View>
          <Btn
            title="취소"
            kind="danger"
            onPress={async () => {
              try {
                await api.cancelJob(jobId);
              } catch {
                /* 다음 조회에서 상태가 바뀜 */
              }
            }}
          />
          <Btn title="나중에 보기 (서버는 계속 작업합니다)" kind="ghost" onPress={onLeave} />
        </View>
      ) : null}
    </ScrollView>
  );
}
