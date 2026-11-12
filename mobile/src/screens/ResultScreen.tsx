// 5단계: PDF 받기·열기 / 6단계: 구글 드라이브에 저장
import * as Sharing from 'expo-sharing';
import React, { useEffect, useState } from 'react';
import { Linking, ScrollView, Text } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Api, JobStatus } from '../api';
import { Settings } from '../storage';
import { Bar, Btn, C, Card, Label, Note, StepBadge } from '../ui';

function fmtSize(n: number): string {
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))}KB`;
  return `${(n / 1024 / 1024).toFixed(1)}MB`;
}

export function ResultScreen({
  api,
  initial,
  settings,
  onNew,
  onSettings,
}: {
  api: Api;
  initial: JobStatus;
  settings: Settings;
  onNew: () => void;
  onSettings: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [job, setJob] = useState<JobStatus>(initial);
  const [dlPct, setDlPct] = useState<number | null>(null);
  const [localUri, setLocalUri] = useState('');
  const [err, setErr] = useState('');
  const [uploading, setUploading] = useState(false);

  const canDrive = !!settings.googleSession && !!settings.driveFolderId;
  const drive = job.drive;

  // 드라이브 업로드 중이면 끝날 때까지 상태를 확인
  useEffect(() => {
    if (drive.status !== 'uploading') return;
    const t = setInterval(async () => {
      try {
        setJob(await api.getJob(job.id));
      } catch {
        /* 다음 번에 다시 */
      }
    }, 1500);
    return () => clearInterval(t);
  }, [drive.status, api, job.id]);

  const openPdf = async () => {
    setErr('');
    try {
      let uri = localUri;
      if (!uri) {
        setDlPct(0);
        uri = await api.downloadPdf(job.id, job.pdf?.name ?? job.output_name, (w, t) =>
          setDlPct(t > 0 ? w / t : 0),
        );
        setLocalUri(uri);
      }
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf', dialogTitle: 'PDF 열기 또는 공유' });
      } else {
        setErr('이 기기에서는 공유 창을 열 수 없습니다.');
      }
    } catch (e: any) {
      setErr(e?.message ?? 'PDF 를 받지 못했습니다.');
    } finally {
      setDlPct(null);
    }
  };

  const saveToDrive = async () => {
    setErr('');
    setUploading(true);
    try {
      const d = await api.uploadToDrive(job.id, settings.googleSession, settings.driveFolderId);
      setJob({ ...job, drive: d });
    } catch (e: any) {
      setErr(e?.message ?? '드라이브 저장을 시작하지 못했습니다.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: C.bg }}
      contentContainerStyle={{ padding: 16, paddingTop: insets.top + 12, paddingBottom: insets.bottom + 40 }}
    >
      <Card tone="ok">
        <Text style={{ color: C.ok, fontSize: 20, fontWeight: '800' }}>PDF가 완성되었습니다 🎉</Text>
        <Text style={{ color: C.ink, marginTop: 8, fontSize: 16 }}>{job.book_title}</Text>
        {job.pdf ? (
          <Text style={{ color: C.sub, marginTop: 4 }}>
            {job.pdf.pages}쪽 · {fmtSize(job.pdf.size)} · {job.pdf.name}
          </Text>
        ) : null}
        {job.failed_count > 0 ? (
          <Text style={{ color: C.warn, marginTop: 8 }}>
            불러오지 못한 페이지 {job.failed_count}개가 있습니다 (PDF 안에 안내 문구로 표시됨):{'\n'}
            {job.failed.slice(0, 5).map((f) => `· ${f.title}`).join('\n')}
          </Text>
        ) : null}
      </Card>

      <Card>
        <StepBadge n="5" title="PDF 받기" />
        <Note text="폰으로 내려받은 뒤 PDF 앱으로 열거나, 다른 앱으로 보낼 수 있어요." />
        {dlPct !== null ? (
          <>
            <Label text={`내려받는 중 ${Math.round(dlPct * 100)}%`} />
            <Bar value={dlPct} />
          </>
        ) : null}
        <Btn title={localUri ? 'PDF 열기 / 공유' : 'PDF 받아서 열기'} onPress={openPdf} loading={dlPct !== null} />
      </Card>

      <Card>
        <StepBadge n="6" title="구글 드라이브에 저장" />
        {!canDrive ? (
          <>
            <Note text="처음 화면에서 구글 로그인과 저장 폴더를 지정하면 여기서 바로 저장할 수 있어요." />
            <Btn title="설정에서 지정하기" kind="secondary" onPress={onSettings} />
          </>
        ) : (
          <>
            <Label text="저장할 폴더" />
            <Text style={{ color: C.ink, fontSize: 16 }}>{settings.driveFolderName}</Text>
            {drive.status === 'uploading' ? (
              <Note text="드라이브에 올리는 중입니다…" tone="warn" />
            ) : drive.status === 'done' ? (
              <>
                <Note text="드라이브에 저장되었습니다." tone="ok" />
                {drive.link ? <Btn title="드라이브에서 열기" kind="secondary" onPress={() => Linking.openURL(drive.link!)} /> : null}
              </>
            ) : null}
            {drive.status === 'error' ? <Note text={drive.message ?? '드라이브 저장에 실패했습니다.'} tone="err" /> : null}
            {drive.status !== 'uploading' ? (
              <Btn
                title={drive.status === 'done' ? '한 번 더 저장' : '드라이브에 저장'}
                onPress={saveToDrive}
                loading={uploading}
              />
            ) : null}
          </>
        )}
      </Card>

      {err ? (
        <Card tone="err">
          <Note text={err} tone="err" />
        </Card>
      ) : null}

      <Btn title="새 작업 시작" kind="ghost" onPress={onNew} />
    </ScrollView>
  );
}
