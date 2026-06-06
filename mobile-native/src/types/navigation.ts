export type RootStackParamList = {
  Auth: undefined;
  MainTabs: { initialTab?: MainTabName } | undefined;
  Account: undefined;
  VerdictDetail: { code?: string; verdictId?: number };
  Payment: { topUpAmount?: number } | undefined;
};

export type MainTabParamList = {
  Home: { brand?: string } | undefined;
  Check: { brand?: string; order?: 'category-brand' | 'brand-category' } | undefined;
  Verdicts: undefined;
};

export type MainTabName = keyof MainTabParamList;
