export type AuthUser = {
  tgId: number;
  name: string;
  username?: string | null;
  img: string;
  balance: string;
};

export type VerdictPhoto = {
  id: number;
  image_url?: string;
  image?: string;
  uploaded_at?: string;
};

export type Verdict = {
  id: number;
  code: string;
  status: 'inpending' | 'todo' | 'fake' | 'legit' | 'dont_payment' | string;
  status_display?: string;
  category: string;
  category_display?: string;
  brand: string;
  item_model?: string;
  comment?: string;
  comment_from_user?: string;
  created_at: string;
  speed?: string;
  price?: string;
  with_reason?: boolean;
  photos: VerdictPhoto[];
  first_photo_url?: string | null;
};

export type LoginTokenResponse = {
  token: string;
  expires_at_ts: number;
};

export type PollTokenResponse =
  | { authenticated: false; expired?: boolean }
  | { authenticated: true; user: AuthUser };
