import { StatusBar } from 'expo-status-bar';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, BackHandler, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Api, JobStatus } from './src/api';
import { ProgressScreen } from './src/screens/ProgressScreen';
import { ResultScreen } from './src/screens/ResultScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { DEFAULTS, loadSettings, saveSettings, Settings } from './src/storage';
import { C } from './src/ui';

type Screen = 'loading' | 'settings' | 'progress' | 'result';

export default function App() {
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [screen, setScreen] = useState<Screen>('loading');
  const [result, setResult] = useState<JobStatus | null>(null);
  const settingsRef = useRef(settings);
  settingsRef.current = settings;

  const api = useMemo(() => new Api(settings.serverUrl, settings.apiKey), [settings.serverUrl, settings.apiKey]);

  const update = useCallback((p: Partial<Settings>) => {
    const next = { ...settingsRef.current, ...p };
    settingsRef.current = next;
    setSettings(next);
    saveSettings(next);
  }, []);

  // 앱을 켤 때: 저장된 설정을 읽고, 전에 시작한 작업이 있으면 이어서 보여줌
  useEffect(() => {
    (async () => {
      const s = await loadSettings();
      settingsRef.current = s;
      setSettings(s);
      if (s.lastJobId && s.serverUrl && s.apiKey) {
        try {
          const j = await new Api(s.serverUrl, s.apiKey).getJob(s.lastJobId);
          if (j.status === 'done') {
            setResult(j);
            setScreen('result');
          } else if (j.status === 'queued' || j.status === 'running') {
            setScreen('progress');
          } else {
            setScreen('settings');
          }
          return;
        } catch {
          /* 서버가 잊었거나 연결 안 됨 → 설정 화면으로 */
        }
      }
      setScreen('settings');
    })();
  }, []);

  // 안드로이드 뒤로가기: 진행/결과 화면에서는 설정 화면으로 (작업은 서버에서 계속됨)
  useEffect(() => {
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (screen === 'progress' || screen === 'result') {
        setScreen('settings');
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, [screen]);

  const openActive = useCallback(async () => {
    try {
      const j = await api.getJob(settingsRef.current.lastJobId);
      if (j.status === 'done') {
        setResult(j);
        setScreen('result');
      } else {
        setScreen('progress');
      }
    } catch {
      update({ lastJobId: '' });
    }
  }, [api, update]);

  const handleDone = useCallback((j: JobStatus) => {
    setResult(j);
    setScreen('result');
  }, []);

  const resetAll = useCallback(() => {
    update({ lastJobId: '' });
    setResult(null);
    setScreen('settings');
  }, [update]);

  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      {screen === 'loading' ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: C.bg }}>
          <ActivityIndicator size="large" color={C.primary} />
        </View>
      ) : null}
      {screen === 'settings' ? (
        <SettingsScreen
          settings={settings}
          update={update}
          api={api}
          activeJobId={settings.lastJobId}
          onStarted={(id) => {
            update({ lastJobId: id });
            setResult(null);
            setScreen('progress');
          }}
          onOpenActive={openActive}
        />
      ) : null}
      {screen === 'progress' ? (
        <ProgressScreen
          api={api}
          jobId={settings.lastJobId}
          onDone={handleDone}
          onLeave={() => setScreen('settings')}
          onReset={resetAll}
        />
      ) : null}
      {screen === 'result' && result ? (
        <ResultScreen
          api={api}
          initial={result}
          settings={settings}
          onNew={resetAll}
          onSettings={() => setScreen('settings')}
        />
      ) : null}
    </SafeAreaProvider>
  );
}
