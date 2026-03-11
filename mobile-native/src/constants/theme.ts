export const colors = {
  bg: '#0c0f16',
  card: '#11151a',
  cardAlt: '#171c24',
  text: '#ffffff',
  muted: '#464f5d',
  success: '#13cd90',
  successDark: '#1d785b',
  danger: '#ff5151',
  warning: '#ffc107',
  blue: '#268bff',
  border: 'rgba(179,214,255,0.08)',
};

export const gradients = {
  card: ['#171c24', '#11151a'] as const,
  success: ['#0CC88B', '#1D785B'] as const,
  successSoft: ['rgba(12,200,139,0.1)', 'rgba(29,120,91,0.1)'] as const,
  dangerSoft: ['rgba(255,81,81,0.12)', 'rgba(140,32,32,0.12)'] as const,
  warningSoft: ['rgba(255,193,7,0.14)', 'rgba(140,110,0,0.14)'] as const,
};

export const spacing = {
  page: 16,
  section: 12,
  gap: 8,
};
