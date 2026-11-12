import AsyncStorage from '@react-native-async-storage/async-storage';

export type Settings = {
  serverUrl: string;
  apiKey: string;
  bookUrl: string;
  outputName: string;
  maxPages: string; // 입력칸은 글자로 다루고, 보낼 때 숫자로 바꿈
  delaySec: string;
  includeToc: boolean;
  includeImages: boolean;
  googleSession: string; // 서버가 준 로그인 번호
  googleEmail: string;
  driveFolderId: string;
  driveFolderName: string;
  lastJobId: string;
};

export const DEFAULTS: Settings = {
  serverUrl: '',
  apiKey: '',
  bookUrl: 'https://wikidocs.net/book/17550',
  outputName: 'wikidocs_book.pdf',
  maxPages: '5', // 처음엔 5개만 시험해 보도록
  delaySec: '1',
  includeToc: true,
  includeImages: true,
  googleSession: '',
  googleEmail: '',
  driveFolderId: '',
  driveFolderName: '',
  lastJobId: '',
};

const KEY = 'settings.v1';

export async function loadSettings(): Promise<Settings> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

export async function saveSettings(s: Settings): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* 저장 실패는 화면 사용에 지장 없음 */
  }
}
