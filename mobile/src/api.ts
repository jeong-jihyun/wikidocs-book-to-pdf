// 서버와 주고받는 모든 통신이 이 파일에 모여 있습니다.
import * as FileSystem from 'expo-file-system/legacy';

export type Phase = 'queued' | 'toc' | 'crawl' | 'render' | 'merge' | 'done';
export type DriveState = {
  status: 'idle' | 'uploading' | 'done' | 'error';
  message?: string;
  link?: string;
  file_id?: string;
  name?: string;
};
export type JobStatus = {
  id: string;
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled';
  phase: Phase;
  phase_label: string;
  done: number;
  total: number;
  message: string;
  book_title: string;
  output_name: string;
  logs: string[];
  failed: { title: string; reason: string }[];
  failed_count: number;
  drive: DriveState;
  pdf?: { name: string; size: number; pages: number };
};
export type JobConfig = {
  book_url: string;
  output_name: string;
  max_pages: number;
  delay_sec: number;
  include_toc: boolean;
  include_images: boolean;
};
export type Folder = { id: string; name: string };
export type FolderList = { id: string; name: string; folders: Folder[] };

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function normalizeBase(url: string): string {
  let u = url.trim().replace(/\/+$/, '');
  if (u && !/^https?:\/\//i.test(u)) u = 'https://' + u;
  return u;
}

function detailText(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string };
    return (first?.msg ?? '').replace(/^Value error, /, '');
  }
  return '';
}

export class Api {
  base: string;
  key: string;
  constructor(base: string, key: string) {
    this.base = normalizeBase(base);
    this.key = key.trim();
  }

  private async req<T>(
    path: string,
    opts: { method?: string; body?: unknown; timeout?: number } = {},
  ): Promise<T> {
    if (!this.base) throw new ApiError(0, '서버 주소를 먼저 입력해 주세요.');
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), opts.timeout ?? 30000);
    try {
      const res = await fetch(this.base + path, {
        method: opts.method ?? 'GET',
        headers: { 'X-API-Key': this.key, 'Content-Type': 'application/json' },
        body: opts.body ? JSON.stringify(opts.body) : undefined,
        signal: ctrl.signal,
      });
      const text = await res.text();
      let data: any = null;
      try {
        data = JSON.parse(text);
      } catch {
        /* JSON 이 아닌 응답 */
      }
      if (!res.ok) {
        throw new ApiError(res.status, detailText(data?.detail) || `서버 오류(${res.status})`);
      }
      return data as T;
    } catch (e: any) {
      if (e instanceof ApiError) throw e;
      if (e?.name === 'AbortError') {
        throw new ApiError(0, '서버 응답이 없습니다. 무료 서버는 잠들어 있다가 깨어나는 데 1분쯤 걸릴 수 있으니 잠시 뒤 다시 눌러 주세요.');
      }
      throw new ApiError(0, '서버에 연결할 수 없습니다. 서버 주소와 인터넷 연결을 확인해 주세요.');
    } finally {
      clearTimeout(timer);
    }
  }

  // 서버가 살아있는지 + API 키가 맞는지
  health() {
    return this.req<{ ok: boolean; version: string; google_configured: boolean }>('/health', { timeout: 70000 });
  }
  ping() {
    return this.req<{ ok: boolean; google_configured: boolean }>('/ping', { timeout: 70000 });
  }

  // 2~4단계: 설정값을 보내 변환을 시작하고, 진행 상황을 읽음
  createJob(cfg: JobConfig) {
    return this.req<{ id: string }>('/jobs', { method: 'POST', body: cfg, timeout: 70000 });
  }
  getJob(id: string) {
    return this.req<JobStatus>(`/jobs/${id}`);
  }
  cancelJob(id: string) {
    return this.req<{ ok: boolean }>(`/jobs/${id}`, { method: 'DELETE' });
  }

  // 5단계: 완성된 PDF 를 폰으로 내려받기 (받은 파일의 경로를 돌려줌)
  async downloadPdf(
    id: string,
    fileName: string,
    onProgress: (written: number, total: number) => void,
  ): Promise<string> {
    const ascii = fileName.replace(/[^\w.\-]+/g, '_');
    const safe = /^_*\.pdf$/i.test(ascii) || !ascii ? `wikidocs_${id}.pdf` : ascii;
    const dest = (FileSystem.cacheDirectory ?? '') + safe;
    const task = FileSystem.createDownloadResumable(
      `${this.base}/jobs/${id}/pdf`,
      dest,
      { headers: { 'X-API-Key': this.key } },
      (p) => onProgress(p.totalBytesWritten, p.totalBytesExpectedToWrite),
    );
    const r = await task.downloadAsync();
    if (!r || r.status !== 200) {
      throw new ApiError(r?.status ?? 0, 'PDF 를 내려받지 못했습니다. 다시 시도해 주세요.');
    }
    return r.uri;
  }

  // 6단계: 구글 로그인, 폴더 고르기, 드라이브에 저장
  googleStart() {
    return this.req<{ session_id: string; url: string }>('/auth/google/start', { method: 'POST' });
  }
  googleSession(sid: string) {
    return this.req<{ signed_in: boolean; email: string }>(`/auth/session/${encodeURIComponent(sid)}`);
  }
  googleLogout(sid: string) {
    return this.req<{ ok: boolean }>(`/auth/session/${encodeURIComponent(sid)}`, { method: 'DELETE' });
  }
  folders(sid: string, parent: string) {
    return this.req<FolderList>(
      `/drive/folders?session=${encodeURIComponent(sid)}&parent=${encodeURIComponent(parent)}`,
    );
  }
  uploadToDrive(jobId: string, sid: string, folderId: string) {
    return this.req<DriveState>(`/jobs/${jobId}/drive`, {
      method: 'POST',
      body: { session_id: sid, folder_id: folderId },
    });
  }
}
