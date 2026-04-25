export default function Sparkline({ data, color, width = 80, height = 26 }) {
  if (!data || data.length < 2) return <span style={{ display: 'inline-block', width }} />;

  const vals = data.filter(v => v !== null && v !== undefined);
  const max = Math.max(...vals);
  const min = Math.min(...vals);
  const range = max - min || 1;

  const autoColor = vals[vals.length - 1] >= vals[0] ? '#22c55e' : '#ef4444';
  const strokeColor = color || autoColor;

  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * width;
    const y = (height - 3) - ((v - min) / range) * (height - 6) + 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  // Fill area under the line
  const first = pts.split(' ')[0];
  const last  = pts.split(' ').at(-1);
  const fillPts = `${first.split(',')[0]},${height} ${pts} ${last.split(',')[0]},${height}`;

  return (
    <svg width={width} height={height} style={{ display: 'block', overflow: 'visible' }}>
      <polygon points={fillPts} fill={strokeColor} opacity="0.12" />
      <polyline fill="none" stroke={strokeColor} strokeWidth="1.5" strokeLinejoin="round" points={pts} />
    </svg>
  );
}
