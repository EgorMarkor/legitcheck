import { API_BASE_URL } from '../constants/config';
import { AuthUser, LoginTokenResponse, PollTokenResponse, Verdict } from './types';

export type MobileImageFile = {
  uri: string;
  name?: string;
  type?: string;
};

class HttpError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, message: string, payload: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

const STATUS_LABELS: Record<string, string> = {
  inpending: 'В обработке',
  todo: 'Требует действия',
  fake: 'Подделка',
  legit: 'Оригинал',
  dont_payment: 'Не оплачено',
};

const CATEGORY_LABELS: Record<string, string> = {
  sneakers: 'Кроссовки',
  clothes: 'Одежда',
  bags: 'Сумки',
  belts: 'Ремни',
  watch: 'Часы',
  cosmetics: 'Косметика',
  jewerly: 'Украшения',
  toys: 'Игрушки',
  accsesory: 'Аксессуары',
  others: 'Другое',
};

function errorMessageFromPayload(payload: unknown, status: number): string {
  if (typeof payload === 'object' && payload) {
    const typedPayload = payload as Record<string, unknown>;
    const candidate = typedPayload.error ?? typedPayload.detail ?? typedPayload.message;
    if (typeof candidate === 'string' && candidate.trim()) {
      const htmlCandidate = candidate.toLowerCase();
      if (htmlCandidate.includes('<!doctype html') || htmlCandidate.includes('<html')) {
        if (status === 404) {
          return 'Вердикт не найден';
        }
        return 'Сервис временно недоступен';
      }
      return candidate;
    }
  }

  if (status === 404) {
    return 'Вердикт не найден';
  }

  return `Request failed with status ${status}`;
}

function asVerdictList(payload: Verdict[] | { results?: Verdict[] } | unknown): Verdict[] {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (typeof payload === 'object' && payload && Array.isArray((payload as { results?: Verdict[] }).results)) {
    return (payload as { results: Verdict[] }).results;
  }

  return [];
}

function normalizeVerdict(verdict: Verdict): Verdict {
  const photos = Array.isArray(verdict.photos)
    ? verdict.photos.map((photo) => ({
      ...photo,
      image_url: photo.image_url ?? (typeof photo.image === 'string' ? photo.image : undefined),
    }))
    : [];

  return {
    ...verdict,
    code: String(verdict.code ?? '').trim().toUpperCase(),
    status_display: verdict.status_display ?? STATUS_LABELS[verdict.status] ?? 'В обработке',
    category_display: verdict.category_display ?? CATEGORY_LABELS[verdict.category] ?? verdict.category,
    item_model: verdict.item_model ?? '',
    comment: verdict.comment ?? '',
    comment_from_user: verdict.comment_from_user ?? '',
    photos,
    first_photo_url: verdict.first_photo_url ?? photos[0]?.image_url ?? photos[0]?.image ?? null,
  };
}

function findVerdictByCode(items: Verdict[], code: string): Verdict | null {
  const wantedCode = code.toUpperCase();
  return items.find((item) => String(item.code ?? '').toUpperCase() === wantedCode) ?? null;
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  const text = await response.text();
  let payload: unknown = {};

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { error: text };
    }
  }

  if (!response.ok) {
    const errorMessage = errorMessageFromPayload(payload, response.status);
    throw new HttpError(response.status, errorMessage, payload);
  }

  return payload as T;
}

export function createLoginToken() {
  return requestJson<LoginTokenResponse>('/api/auth/token/', {
    method: 'POST',
  });
}

export function pollLoginToken(token: string) {
  return requestJson<PollTokenResponse>(`/api/auth/poll/${encodeURIComponent(token)}/`);
}

export function fetchUser(tgId: number) {
  return requestJson<AuthUser>(`/api/users/${tgId}/`);
}

export function fetchUserVerdicts(tgId: number) {
  return requestJson<Verdict[] | { results?: Verdict[] }>(
    `/api/verdicts/?user_id=${encodeURIComponent(String(tgId))}`
  ).then((items) => asVerdictList(items).map(normalizeVerdict));
}

export async function fetchVerdictByCode(code: string) {
  const normalizedCode = String(code ?? '').trim().toUpperCase();
  if (!normalizedCode) {
    throw new Error('Код вердикта не указан');
  }

  try {
    const payload = await requestJson<{ success: boolean; verdict: Verdict }>(
      `/api/mobile/verdict/by-code/${encodeURIComponent(normalizedCode)}/`
    );
    return normalizeVerdict(payload.verdict);
  } catch (error) {
    const isMissingMobileEndpoint = (
      error instanceof HttpError &&
      (error.status === 404 || error.status === 405 || error.status >= 500)
    );

    if (!isMissingMobileEndpoint) {
      throw error;
    }
  }

  const filteredResponse = await requestJson<Verdict[] | { results?: Verdict[] }>(
    `/api/verdicts/?code=${encodeURIComponent(normalizedCode)}`
  );
  const fromFiltered = findVerdictByCode(asVerdictList(filteredResponse), normalizedCode);
  if (fromFiltered) {
    return normalizeVerdict(fromFiltered);
  }

  const listResponse = await requestJson<Verdict[] | { results?: Verdict[] }>('/api/verdicts/');
  const fromList = findVerdictByCode(asVerdictList(listResponse), normalizedCode);
  if (fromList) {
    return normalizeVerdict(fromList);
  }

  throw new Error('Вердикт не найден');
}

export async function uploadDraftPhotos(tgId: number, files: MobileImageFile[]) {
  const formData = new FormData();
  formData.append('tg_id', String(tgId));

  files.forEach((file, index) => {
    formData.append('photos', {
      uri: file.uri,
      type: file.type ?? 'image/jpeg',
      name: file.name ?? `photo-${Date.now()}-${index}.jpg`,
    } as unknown as Blob);
  });

  return requestJson<{ success: boolean; photo_ids: number[]; photos: { id: number; image_url: string }[] }>(
    '/api/mobile/verdict/photos/upload/',
    {
      method: 'POST',
      body: formData,
    }
  );
}

export async function createMobileVerdict(input: {
  tgId: number;
  category: string;
  brand: string;
  item_model?: string;
  comment?: string;
  speed: string;
  with_reason: boolean;
  photo_ids: number[];
}) {
  return requestJson<{ success: boolean; verdict: Verdict }>(
    '/api/mobile/verdict/create/',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        tg_id: input.tgId,
        category: input.category,
        brand: input.brand,
        item_model: input.item_model ?? '',
        comment: input.comment ?? '',
        speed: input.speed,
        with_reason: input.with_reason,
        photo_ids: input.photo_ids,
      }),
    }
  );
}

export async function uploadPhotoToVerdict(verdictId: number, tgId: number, file: MobileImageFile) {
  const formData = new FormData();
  formData.append('tg_id', String(tgId));
  formData.append('photo', {
    uri: file.uri,
    type: file.type ?? 'image/jpeg',
    name: file.name ?? `verdict-photo-${Date.now()}.jpg`,
  } as unknown as Blob);

  return requestJson<{ success: boolean; verdict: Verdict }>(
    `/api/mobile/verdict/${verdictId}/upload-photo/`,
    {
      method: 'POST',
      body: formData,
    }
  );
}

export async function createYookassaPayment(userId: number, amount: number) {
  return requestJson<{ url: string }>(
    '/api/payment/create-yookassa/',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        user_id: userId,
        amount: amount.toFixed(2),
      }),
    }
  );
}
