// 2단계: 설정값 입력 (서버 연결, 책 주소, 옵션) + 6단계 준비(구글 로그인, 드라이브 폴더 지정)
import * as WebBrowser from 'expo-web-browser';
import React, { useMemo, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Api, JobConfig } from '../api';
import { Settings } from '../storage';
import { Btn, Card, C, Field, Label, Note, StepBadge, SwitchRow } from '../ui';
import { FolderPicker } from './FolderPicker';

const BOOK_RE = /^https:\/\/wikidocs\.net\/book\/\d+\/?$/;

type Msg = { tone: 'ok' | 'warn' | 'err'; text: string } | null;

export function SettingsScreen({
  settings,
  update,
  api,
  activeJobId,
  onStarted,
  onOpenActive,
}: {
  settings: Settings;
  update: (p: Partial<Settings>) => void;
  api: Api;
  activeJobId: string;
  onStarted: (jobId: string) => void;
  onOpenActive: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [serverMsg, setServerMsg] = useState<Msg>(null);
  const [loggingIn, setLoggingIn] = useState(false);
  const [driveMsg, setDriveMsg] = useState<Msg>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startMsg, setStartMsg] = useState<Msg>(null);

  const signedIn = !!settings.googleSession && !!settings.googleEmail;

  const testServer = async () => {
    setTesting(true);
    setServerMsg({ tone: 'warn', text: '서버에 연결하는 중… (잠든 서버는 1분쯤 걸려요)' });
    try {
      await api.health();
      const p = await api.ping();
      setServerMsg({
        tone: 'ok',
        text: p.google_configured
          ? '연결 성공 · API 키 확인됨 · 구글 로그인 준비됨'
          : '연결 성공 · API 키 확인됨 · (서버에 구글 로그인 설정이 아직 없어요)',
      });
    } catch (e: any) {
      setServerMsg({ tone: 'err', text: e?.message ?? '연결에 실패했습니다.' });
    } finally {
      setTesting(false);
    }
  };

  const googleLogin = async () => {
    setLoggingIn(true);
    setDriveMsg(null);
    try {
      const { session_id, url } = await api.googleStart();
      await WebBrowser.openAuthSessionAsync(url, 'wikidocs2pdf://auth');
      // 브라우저 창을 닫은 뒤, 서버가 로그인을 확인했는지 잠깐 기다리며 확인
      for (let i = 0; i < 8; i++) {
        const info = await api.googleSession(session_id);
        if (info.signed_in) {
          update({ googleSession: session_id, googleEmail: info.email || '로그인됨', driveFolderId: '', driveFolderName: '' });
          setDriveMsg({ tone: 'ok', text: '구글 로그인이 완료되었습니다. 이제 저장할 폴더를 골라 주세요.' });
          return;
        }
        await new Promise((r) => setTimeout(r, 1000));
      }
      setDriveMsg({ tone: 'warn', text: '로그인이 끝나지 않았습니다. 구글 화면에서 끝까지 진행한 뒤 다시 눌러 주세요.' });
    } catch (e: any) {
      setDriveMsg({ tone: 'err', text: e?.message ?? '구글 로그인에 실패했습니다.' });
    } finally {
      setLoggingIn(false);
    }
  };

  const googleLogout = async () => {
    try {
      if (settings.googleSession) await api.googleLogout(settings.googleSession);
    } catch {
      /* 서버가 이미 잊었어도 상관없음 */
    }
    update({ googleSession: '', googleEmail: '', driveFolderId: '', driveFolderName: '' });
    setDriveMsg(null);
  };

  const cfg = useMemo(() => {
    const maxPages = parseInt(settings.maxPages || '0', 10);
    const delay = parseFloat((settings.delaySec || '1').replace(',', '.'));
    return { maxPages, delay };
  }, [settings.maxPages, settings.delaySec]);

  const start = async () => {
    setStartMsg(null);
    if (!settings.serverUrl.trim()) return setStartMsg({ tone: 'err', text: '서버 주소를 입력해 주세요.' });
    if (!settings.apiKey.trim()) return setStartMsg({ tone: 'err', text: 'API 키를 입력해 주세요.' });
    if (!BOOK_RE.test(settings.bookUrl.trim()))
      return setStartMsg({ tone: 'err', text: '책 주소는 https://wikidocs.net/book/숫자 형식이어야 합니다.' });
    if (Number.isNaN(cfg.maxPages) || cfg.maxPages < 0)
      return setStartMsg({ tone: 'err', text: '변환할 페이지 수는 0 이상의 숫자로 입력해 주세요. (0 = 전체)' });
    if (Number.isNaN(cfg.delay) || cfg.delay < 0 || cfg.delay > 30)
      return setStartMsg({ tone: 'err', text: '요청 간격은 0~30 사이 숫자(초)로 입력해 주세요.' });

    const body: JobConfig = {
      book_url: settings.bookUrl.trim(),
      output_name: settings.outputName.trim() || 'wikidocs_book.pdf',
      max_pages: cfg.maxPages,
      delay_sec: cfg.delay,
      include_toc: settings.includeToc,
      include_images: settings.includeImages,
    };
    setStarting(true);
    try {
      const { id } = await api.createJob(body);
      onStarted(id);
    } catch (e: any) {
      setStartMsg({ tone: 'err', text: e?.message ?? '시작하지 못했습니다.' });
    } finally {
      setStarting(false);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        style={{ flex: 1, backgroundColor: C.bg }}
        contentContainerStyle={{ padding: 16, paddingTop: insets.top + 12, paddingBottom: insets.bottom + 40 }}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={{ fontSize: 24, fontWeight: '800', color: C.ink }}>위키독스 → PDF</Text>
        <Text style={{ color: C.sub, marginTop: 4, marginBottom: 16 }}>
          책 주소만 넣으면 서버가 모든 페이지를 모아 PDF 한 권으로 만들어 줍니다.
        </Text>

        {activeJobId ? (
          <Card tone="warn">
            <Text style={{ color: C.warn, fontWeight: '700' }}>이전에 시작한 작업이 있어요</Text>
            <Btn title="진행 상황 / 결과 보기" kind="secondary" onPress={onOpenActive} />
          </Card>
        ) : null}

        <Card>
          <StepBadge n="2" title="서버 연결" />
          <Field
            label="서버 주소"
            hint="Render 에 올린 서버 주소 (예: https://wikidocs-book-to-pdf.onrender.com)"
            value={settings.serverUrl}
            onChangeText={(v) => update({ serverUrl: v })}
            keyboardType="url"
            placeholder="https://...onrender.com"
          />
          <Field
            label="API 키"
            hint="Render 환경변수 API_KEY 값을 그대로 붙여넣으세요"
            value={settings.apiKey}
            onChangeText={(v) => update({ apiKey: v })}
            secureTextEntry={!showKey}
            placeholder="붙여넣기"
          />
          <Btn title={showKey ? 'API 키 숨기기' : 'API 키 보기'} kind="ghost" onPress={() => setShowKey(!showKey)} />
          <Btn title="연결 테스트" kind="secondary" onPress={testServer} loading={testing} />
          {serverMsg ? <View style={{ marginTop: 10 }}><Note text={serverMsg.text} tone={serverMsg.tone} /></View> : null}
        </Card>

        <Card>
          <StepBadge n="2" title="책과 변환 옵션" />
          <Field
            label="책 주소"
            value={settings.bookUrl}
            onChangeText={(v) => update({ bookUrl: v })}
            keyboardType="url"
            placeholder="https://wikidocs.net/book/17550"
          />
          <Field label="PDF 파일 이름" value={settings.outputName} onChangeText={(v) => update({ outputName: v })} />
          <Field
            label="변환할 페이지 수"
            hint="0 = 전체. 처음엔 5 정도로 시험해 보세요 (앞에서부터 그 개수만)"
            value={settings.maxPages}
            onChangeText={(v) => update({ maxPages: v.replace(/[^0-9]/g, '') })}
            keyboardType="number-pad"
          />
          <Field
            label="요청 간격(초)"
            hint="위키독스 서버에 부담을 주지 않도록 페이지 사이에 쉬는 시간. 기본 1"
            value={settings.delaySec}
            onChangeText={(v) => update({ delaySec: v.replace(/[^0-9.,]/g, '') })}
            keyboardType="decimal-pad"
          />
          <SwitchRow label="PDF 앞에 목차 넣기" value={settings.includeToc} onChange={(v) => update({ includeToc: v })} />
          <SwitchRow
            label="그림 포함하기"
            hint="끄면 더 빠르고 파일이 작아집니다"
            value={settings.includeImages}
            onChange={(v) => update({ includeImages: v })}
          />
        </Card>

        <Card>
          <StepBadge n="6" title="구글 드라이브에 저장 (선택)" />
          {signedIn ? (
            <>
              <Label text="로그인한 계정" />
              <Text style={{ color: C.ink, fontSize: 16 }}>{settings.googleEmail}</Text>
              <Label text="저장할 폴더" />
              <Text style={{ color: settings.driveFolderId ? C.ink : C.sub, fontSize: 16 }}>
                {settings.driveFolderId ? settings.driveFolderName : '아직 고르지 않았어요'}
              </Text>
              <Btn title={settings.driveFolderId ? '폴더 다시 고르기' : '저장할 폴더 고르기'} onPress={() => setPickerOpen(true)} />
              <Btn title="구글 로그아웃" kind="ghost" onPress={googleLogout} />
            </>
          ) : (
            <>
              <Note text="로그인하면 완성된 PDF 를 내 드라이브 폴더에 바로 저장할 수 있어요. 건너뛰어도 폰으로 받을 수 있습니다." />
              <Btn title="구글 계정으로 로그인" kind="secondary" onPress={googleLogin} loading={loggingIn} />
            </>
          )}
          {driveMsg ? <View style={{ marginTop: 10 }}><Note text={driveMsg.text} tone={driveMsg.tone} /></View> : null}
        </Card>

        {startMsg ? (
          <Card tone={startMsg.tone}>
            <Note text={startMsg.text} tone={startMsg.tone} />
          </Card>
        ) : null}
        <Btn title="변환 시작" onPress={start} loading={starting} />
        <Text style={{ color: C.sub, fontSize: 12, marginTop: 14, lineHeight: 18 }}>
          본인이 열람할 수 있는 공개 책을 개인 소장용으로 변환하는 용도로만 사용하세요. 저작권은 원저자에게 있습니다.
        </Text>
      </ScrollView>

      <FolderPicker
        visible={pickerOpen}
        api={api}
        session={settings.googleSession}
        onClose={() => setPickerOpen(false)}
        onPick={(f) => {
          update({ driveFolderId: f.id, driveFolderName: f.name });
          setPickerOpen(false);
        }}
      />
    </KeyboardAvoidingView>
  );
}
