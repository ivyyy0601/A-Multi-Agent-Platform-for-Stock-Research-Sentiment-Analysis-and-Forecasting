import type { Message } from '../stores/agentChatStore';

/**
 * Format chat messages as Markdown for export.
 */
export function formatSessionAsMarkdown(messages: Message[]): string {
  const now = new Date();
  const timeStr = now.toLocaleString('en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'America/New_York',
    timeZoneName: 'short',
  });

  const lines: string[] = [
    '# Stock Chat Session',
    '',
    `Generated: ${timeStr}`,
    '',
  ];

  for (const msg of messages) {
    const heading = msg.role === 'user' ? '## User' : '## AI';
    if (msg.role === 'assistant' && msg.strategyName) {
      lines.push(`${heading} (${msg.strategyName})`);
    } else {
      lines.push(heading);
    }
    lines.push('');
    lines.push(msg.content);
    lines.push('');
  }

  return lines.join('\n');
}

/**
 * Trigger browser download of session as .md file.
 * Revokes object URL after download to prevent memory leak.
 */
export function downloadSession(messages: Message[]): void {
  const content = formatSessionAsMarkdown(messages);
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const now = new Date();
  const nyParts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(now);
  const get = (t: string) => nyParts.find(p => p.type === t)?.value ?? '';
  const dateStr = `${get('year')}${get('month')}${get('day')}`;
  const timeStr = `${get('hour')}${get('minute')}`;
  const filename = `stock-chat_${dateStr}_${timeStr}.md`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
