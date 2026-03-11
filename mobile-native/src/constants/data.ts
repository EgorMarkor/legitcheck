import { staticUrl } from './config';

export type BrandItem = {
  id: string;
  title: string;
  image: string;
  category: 'sneakers' | 'clothes' | 'premium' | 'popular';
};

export const promoImages = [
  staticUrl('express2.png'),
  staticUrl('express2.png'),
  staticUrl('express2.png'),
];

export const brandItems: BrandItem[] = [
  { id: 'yeezy', title: 'Yeezy', image: staticUrl('yeezy.png'), category: 'sneakers' },
  { id: 'nike', title: 'Nike', image: staticUrl('nike.png'), category: 'sneakers' },
  { id: 'newbalance', title: 'New Balance', image: staticUrl('newbalance.png'), category: 'sneakers' },
  { id: 'stoneisland', title: 'Stone Island', image: staticUrl('stoneisland.png'), category: 'sneakers' },
  { id: 'supreme', title: 'Supreme', image: staticUrl('supreme.png'), category: 'clothes' },
  { id: 'palmangels', title: 'Palm Angels', image: staticUrl('palmangels.png'), category: 'clothes' },
  { id: 'balenciaga', title: 'Balenciaga', image: staticUrl('balenciaga.png'), category: 'premium' },
  { id: 'dior', title: 'Dior', image: staticUrl('dior.png'), category: 'premium' },
  { id: 'louisvuitton', title: 'Louis Vuitton', image: staticUrl('louisvuitton.png'), category: 'premium' },
  { id: 'nb', title: 'NB', image: staticUrl('nb.png'), category: 'popular' },
  { id: 'eye', title: 'Eye', image: staticUrl('eye.png'), category: 'popular' },
  { id: 'champion', title: 'Champion', image: staticUrl('champion.png'), category: 'popular' },
];

export const categories = [
  { id: 'sneakers', title: 'Кроссовки' },
  { id: 'clothes', title: 'Одежда' },
  { id: 'bags', title: 'Сумки' },
  { id: 'belts', title: 'Ремни' },
  { id: 'watch', title: 'Часы' },
  { id: 'cosmetics', title: 'Косметика' },
  { id: 'jewerly', title: 'Украшения' },
  { id: 'toys', title: 'Игрушки' },
  { id: 'accsesory', title: 'Аксессуары' },
  { id: 'others', title: 'Другое' },
] as const;

export const tariffOptions = [
  { id: '24h', title: 'Стандарт (24ч)', price: 450 },
  { id: '15min-basic', title: 'Срочно (15 мин)', price: 600 },
  { id: '15min-expensive', title: 'Срочно PRO (15 мин)', price: 650 },
] as const;

export const reasonPrice = 150;
