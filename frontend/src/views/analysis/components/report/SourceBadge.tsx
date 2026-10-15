
type Source = 'yf' | 'ai' | 'db' | 'calc';

const CONFIG: Record<Source, { label: string; cls: string }> = {
  yf:   { label: 'yfinance', cls: 'bg-cyan/10 text-cyan border-cyan/20' },
  ai:   { label: 'AI',       cls: 'bg-purple-400/10 text-purple-400 border-purple-400/20' },
  db:   { label: 'DB',       cls: 'bg-emerald-400/10 text-emerald-400 border-emerald-400/20' },
  calc: { label: 'Calc',     cls: 'bg-blue-400/10 text-blue-400 border-blue-400/20' },
};

export function SourceBadge({ source, fetchedAt }: { source: Source; fetchedAt?: string }) {
  const { label, cls } = CONFIG[source];
  const timeStr = fetchedAt ? formatTime(fetchedAt) : null;
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`inline-block rounded px-1 py-0.5 text-[10px] font-medium border ${cls}`}>
        {label}
      </span>
      {timeStr && (
        <span className="text-[10px] text-muted-text">{timeStr}</span>
      )}
    </span>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat('en-US', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'America/New_York',
      hour12: false,
    }).format(d).replace(',', '');
  } catch {
    return iso.slice(0, 16);
  }
}
