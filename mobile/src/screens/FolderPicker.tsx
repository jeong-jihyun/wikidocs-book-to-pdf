// 6단계: 내 구글 드라이브에서 저장할 폴더를 고르는 창
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Api, Folder } from '../api';
import { Btn, C, Note } from '../ui';

type Crumb = { id: string; name: string };
const ROOT: Crumb = { id: 'root', name: '내 드라이브' };
const SHARED: Crumb = { id: 'shared', name: '공유 문서함' };

export function FolderPicker({
  visible,
  api,
  session,
  onClose,
  onPick,
}: {
  visible: boolean;
  api: Api;
  session: string;
  onClose: () => void;
  onPick: (f: { id: string; name: string }) => void;
}) {
  const insets = useSafeAreaInsets();
  const [stack, setStack] = useState<Crumb[]>([ROOT]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const reqNo = useRef(0); // 빨리 눌러 이동했을 때 늦게 도착한 옛 응답을 무시하기 위함
  const current = stack[stack.length - 1];

  const load = useCallback(async () => {
    const my = ++reqNo.current;
    setLoading(true);
    setError('');
    try {
      const r = await api.folders(session, current.id);
      if (my === reqNo.current) setFolders(r.folders);
    } catch (e: any) {
      if (my === reqNo.current) {
        setFolders([]);
        setError(e?.message ?? '폴더 목록을 가져오지 못했습니다.');
      }
    } finally {
      if (my === reqNo.current) setLoading(false);
    }
  }, [api, session, current.id]);

  useEffect(() => {
    if (visible) load();
  }, [visible, load]);

  useEffect(() => {
    if (visible) setStack([ROOT]);
  }, [visible]);

  const pathText = stack.map((c) => c.name).join(' / ');

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={[s.wrap, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 8 }]}>
        <Text style={s.title}>저장할 드라이브 폴더 고르기</Text>

        <View style={s.tabs}>
          <Pressable style={[s.tab, stack[0].id === 'root' && s.tabOn]} onPress={() => setStack([ROOT])}>
            <Text style={[s.tabText, stack[0].id === 'root' && s.tabTextOn]}>내 드라이브</Text>
          </Pressable>
          <Pressable style={[s.tab, stack[0].id === 'shared' && s.tabOn]} onPress={() => setStack([SHARED])}>
            <Text style={[s.tabText, stack[0].id === 'shared' && s.tabTextOn]}>공유 문서함</Text>
          </Pressable>
        </View>

        <Text style={s.path} numberOfLines={2}>
          지금 위치: {pathText}
        </Text>
        {stack.length > 1 ? (
          <Pressable style={s.row} onPress={() => setStack(stack.slice(0, -1))}>
            <Text style={s.rowText}>⬆︎  위 폴더로</Text>
          </Pressable>
        ) : null}

        {loading ? <ActivityIndicator style={{ marginVertical: 24 }} color={C.primary} /> : null}
        {error ? (
          <View style={{ marginVertical: 12 }}>
            <Note text={error} tone="err" />
            <Btn title="다시 시도" kind="secondary" onPress={load} />
          </View>
        ) : null}

        <FlatList
          style={{ flex: 1 }}
          data={folders}
          keyExtractor={(f) => f.id}
          ListEmptyComponent={
            !loading && !error ? (
              <Text style={s.empty}>이 위치에는 하위 폴더가 없습니다.{'\n'}아래 버튼으로 여기에 저장할 수 있어요.</Text>
            ) : undefined
          }
          renderItem={({ item }) => (
            <Pressable style={s.row} onPress={() => setStack([...stack, { id: item.id, name: item.name }])}>
              <Text style={s.rowText}>📁  {item.name}</Text>
            </Pressable>
          )}
        />

        <Btn
          title={current.id === 'shared' ? '공유 문서함 안의 폴더를 골라 주세요' : '이 폴더에 저장하기'}
          disabled={current.id === 'shared'}
          onPress={() => onPick({ id: current.id, name: pathText })}
        />
        <Btn title="닫기" kind="ghost" onPress={onClose} />
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: C.bg, paddingHorizontal: 16 },
  title: { fontSize: 19, fontWeight: '800', color: C.ink, marginBottom: 12 },
  tabs: { flexDirection: 'row', marginBottom: 10 },
  tab: { flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center', borderRadius: 10, backgroundColor: '#e8effa', marginRight: 8 },
  tabOn: { backgroundColor: C.primary },
  tabText: { color: C.primary, fontWeight: '700' },
  tabTextOn: { color: '#fff' },
  path: { color: C.sub, fontSize: 14, marginBottom: 8 },
  row: { minHeight: 52, justifyContent: 'center', paddingHorizontal: 14, backgroundColor: '#fff', borderRadius: 10, borderWidth: 1, borderColor: C.line, marginBottom: 8 },
  rowText: { color: C.ink, fontSize: 16 },
  empty: { color: C.sub, textAlign: 'center', marginTop: 24, lineHeight: 22 },
});
