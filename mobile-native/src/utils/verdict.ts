import { API_BASE_URL } from '../constants/config';

export function resolveImageUrl(value?: string | null) {
  if (!value) {
    return undefined;
  }

  if (value.startsWith('http://') || value.startsWith('https://')) {
    return value;
  }

  if (value.startsWith('/')) {
    return `${API_BASE_URL}${value}`;
  }

  return `${API_BASE_URL}/${value}`;
}

export function verdictStatusColor(status: string) {
  if (status === 'legit') {
    return '#35E6AD';
  }

  if (status === 'fake') {
    return '#FF5151';
  }

  if (status === 'todo') {
    return '#FFC107';
  }

  return '#8EA2BC';
}

export function verdictStatusTitle(status: string) {
  if (status === 'legit') {
    return 'Оригинал';
  }
  if (status === 'fake') {
    return 'Подделка';
  }
  if (status === 'todo') {
    return 'Требует действия';
  }
  if (status === 'dont_payment') {
    return 'Не оплачено';
  }
  return 'В обработке';
}
