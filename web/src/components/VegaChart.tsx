/**
 * VegaChart — Renders Vega-Lite specs with the Memphis design system applied.
 *
 * Key behaviors:
 * 1. `patchSpec()` recursively finds every `encoding.color` in the spec tree
 *    and forces the Memphis palette (overrides AI-generated schemes like "tableau10").
 * 2. The Vega config block applies Space Grotesk font, square symbols/points,
 *    hard-bordered bars, and dashed grid lines throughout.
 */
import { useEffect, useRef, useState } from 'react';
import styled from 'styled-components';

/* ── Container ────────────────────────────────────────────────────── */
const ChartContainer = styled.div`
  margin-top: 16px;
  border: 2px solid #0D0D0D;
  border-radius: 0;
  background: #fff;
  box-shadow: 5px 5px 0 #0D0D0D;
  overflow: hidden;
  position: relative;

  /* Memphis left stripe */
  &::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 4px;
    height: 100%;
    background: repeating-linear-gradient(
      180deg,
      #FFE600 0px, #FFE600 8px,
      #FF3366 8px, #FF3366 16px,
      #00D4FF 16px, #00D4FF 24px,
      #0D0D0D 24px, #0D0D0D 32px
    );
    z-index: 2;
  }

  /* Vega embed padding (leave room for left stripe) */
  .vega-embed {
    width: 100%;
    padding: 4px 16px 16px 20px;
  }

  /* Action buttons */
  .vega-embed .vega-actions { top: 6px; right: 8px; }
  .vega-embed .vega-actions a {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 10px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    border: 1.5px solid #0D0D0D !important;
    border-radius: 0 !important;
    box-shadow: 2px 2px 0 #0D0D0D !important;
    color: #0D0D0D !important;
    background: #fff !important;
    padding: 2px 8px !important;
    margin-left: 4px !important;
  }
  .vega-embed .vega-actions a:hover { background: #FFE600 !important; }
`;

/* ── Header (black bar) ───────────────────────────────────────────── */
const ChartHeader = styled.div`
  background: #0D0D0D;
  padding: 7px 14px 7px 18px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 2px solid #0D0D0D;
`;

const ChartTitle = styled.div`
  font-family: 'Space Grotesk', sans-serif;
  font-size: 11px;
  font-weight: 800;
  color: #FFE600;
  text-transform: uppercase;
  letter-spacing: 1px;
  flex: 1;
`;

const ChartTypeBadge = styled.span`
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px;
  font-weight: 800;
  padding: 1px 8px;
  border: 1.5px solid #FFE600;
  background: #FFE600;
  color: #0D0D0D;
  text-transform: uppercase;
  letter-spacing: 0.8px;
`;

/* ── Reasoning callout ───────────────────────────────────────────── */
const ReasoningText = styled.div`
  font-family: 'Space Grotesk', sans-serif;
  font-size: 11px;
  color: #666;
  font-style: italic;
  margin: 8px 20px 0;
  line-height: 1.5;
  padding-bottom: 8px;
  border-bottom: 1px dashed #D0CEC8;
`;

/* ── Error state ─────────────────────────────────────────────────── */
const ErrorBox = styled.div`
  font-family: 'Space Grotesk', sans-serif;
  color: #fff;
  background: #FF3366;
  border-top: 2px solid #0D0D0D;
  padding: 10px 20px;
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

/* ── Types ───────────────────────────────────────────────────────── */
interface VegaChartProps {
  spec: Record<string, any>;
  data?: Record<string, any>[];
  reasoning?: string;
  chartType?: string;
  width?: number;
  height?: number;
}

/* ── Memphis palette (10 vivid, high-contrast colors) ───────────── */
const MEMPHIS_PALETTE = [
  '#FFE600', // yellow   (brand primary — used for first series)
  '#FF3366', // pink
  '#00D4FF', // cyan
  '#FF6B35', // orange
  '#7B2FFF', // purple
  '#00C853', // green
  '#2979FF', // blue
  '#FF1744', // red
  '#00BFA5', // teal
  '#C6FF00', // lime
];

/**
 * Recursively patch every `encoding.color` in a Vega-Lite spec tree
 * to use our Memphis palette, overriding any AI-generated scheme.
 */
function patchSpec(s: any): any {
  if (!s || typeof s !== 'object') return s;
  const p = { ...s };

  if (p.encoding?.color) {
    p.encoding = {
      ...p.encoding,
      color: {
        ...p.encoding.color,
        scale: {
          ...(p.encoding.color.scale || {}),
          range: MEMPHIS_PALETTE,
          scheme: undefined,   // kill "tableau10", "category10", etc.
        },
      },
    };
  }

  for (const key of ['layer', 'concat', 'hconcat', 'vconcat']) {
    if (Array.isArray(p[key])) p[key] = p[key].map(patchSpec);
  }
  if (p.spec && !Array.isArray(p.spec)) p.spec = patchSpec(p.spec);

  return p;
}

/* ── Component ───────────────────────────────────────────────────── */
export default function VegaChart({
  spec,
  data,
  reasoning,
  chartType,
  width = 680,
  height = 380,
}: VegaChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const viewRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current || !spec || Object.keys(spec).length === 0) return;
    let cancelled = false;

    const renderChart = async () => {
      try {
        const vegaEmbed = (await import('vega-embed')).default;

        // 1. Deep-patch the spec to force Memphis colors
        const patchedSpec = patchSpec({ ...spec });

        // 2. Merge Memphis config on top
        const fullSpec: any = {
          ...patchedSpec,
          width: 'container',
          height: height - 60,
          autosize: { type: 'fit', contains: 'padding' },
          background: 'transparent',
          config: {
            ...(patchedSpec.config || {}),

            font: 'Space Grotesk',

            // Fallback palette for non-encoded marks
            range: {
              category: MEMPHIS_PALETTE,
              ordinal: MEMPHIS_PALETTE,
              ramp: ['#FFE600', '#FF6B35', '#FF3366'],
            },

            // ── Axis ─────────────────────────────
            axis: {
              labelFont: 'Space Grotesk',
              labelFontSize: 11,
              labelFontWeight: 700,
              labelColor: '#333',
              titleFont: 'Space Grotesk',
              titleFontSize: 12,
              titleFontWeight: 800,
              titleColor: '#0D0D0D',
              titlePadding: 10,
              gridColor: '#E8E6DF',
              gridDash: [4, 4],
              gridWidth: 1,
              domainColor: '#0D0D0D',
              domainWidth: 2,
              tickColor: '#0D0D0D',
              tickWidth: 2,
              tickSize: 4,
              offset: 4,
            },
            axisX: {
              labelAngle: -30,
              labelLimit: 130,
            },
            axisY: {
              labelAngle: 0,
            },

            // ── Legend ───────────────────────────
            legend: {
              labelFont: 'Space Grotesk',
              labelFontSize: 12,
              labelFontWeight: 600,
              labelColor: '#0D0D0D',
              titleFont: 'Space Grotesk',
              titleFontSize: 11,
              titleFontWeight: 800,
              titleColor: '#0D0D0D',
              titlePadding: 8,
              symbolType: 'square',
              symbolSize: 160,
              symbolStrokeWidth: 1.5,
              symbolStrokeColor: '#0D0D0D',
              padding: 10,
              rowPadding: 5,
              orient: 'right',
            },

            // ── Chart title ───────────────────────
            title: {
              font: 'Space Grotesk',
              fontSize: 13,
              fontWeight: 800,
              color: '#0D0D0D',
              offset: 14,
              anchor: 'start',
            },

            // ── Mark: Bar ────────────────────────
            bar: {
              stroke: '#0D0D0D',
              strokeWidth: 1.5,
              cornerRadiusTopLeft: 0,
              cornerRadiusTopRight: 0,
            },

            // ── Mark: Line ───────────────────────
            line: {
              strokeWidth: 2.5,
              point: {
                filled: true,
                size: 64,
                shape: 'square',
                stroke: '#0D0D0D',
                strokeWidth: 1.5,
              },
            },

            // ── Mark: Point ──────────────────────
            point: {
              filled: true,
              size: 80,
              shape: 'square',
              stroke: '#0D0D0D',
              strokeWidth: 1.5,
            },

            // ── Mark: Area ───────────────────────
            area: {
              stroke: '#0D0D0D',
              strokeWidth: 1.5,
              fillOpacity: 0.65,
              line: true,
            },

            // ── Mark: Arc (pie/donut) ─────────────
            arc: {
              stroke: '#0D0D0D',
              strokeWidth: 1.5,
            },

            // ── View box ─────────────────────────
            view: { stroke: 'transparent' },
          },
        };

        if (data && data.length > 0) {
          fullSpec.data = { values: data };
        }

        if (cancelled) return;

        if (viewRef.current) {
          viewRef.current.finalize();
          viewRef.current = null;
        }

        const result = await vegaEmbed(containerRef.current!, fullSpec, {
          mode: 'vega-lite',
          renderer: 'svg',
          tooltip: { theme: 'custom' },
          actions: { export: true, editor: false, source: false, compiled: false },
        });

        if (!cancelled) {
          viewRef.current = result;
          setError(null);
        }
      } catch (err: any) {
        if (!cancelled) {
          console.error('VegaChart render error:', err);
          setError(err?.message || 'Failed to render chart');
        }
      }
    };

    renderChart();

    return () => {
      cancelled = true;
      if (viewRef.current) {
        viewRef.current.finalize();
        viewRef.current = null;
      }
    };
  }, [spec, data, width, height]);

  if (!spec || Object.keys(spec).length === 0) return null;

  return (
    <ChartContainer>
      <ChartHeader>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#FFE600" strokeWidth="2.5">
          <rect x="18" y="3" width="4" height="18" rx="0"/>
          <rect x="10" y="8" width="4" height="13" rx="0"/>
          <rect x="2"  y="13" width="4" height="8"  rx="0"/>
        </svg>
        <ChartTitle>BIỂU ĐỒ</ChartTitle>
        {chartType && <ChartTypeBadge>{chartType.replace(/_/g, ' ')}</ChartTypeBadge>}
      </ChartHeader>

      {reasoning && (
        <ReasoningText>
          <span style={{ fontWeight: 700, color: '#0D0D0D', fontStyle: 'normal' }}>💡 </span>
          {reasoning}
        </ReasoningText>
      )}

      {error
        ? <ErrorBox>⚠ Lỗi hiển thị biểu đồ: {error}</ErrorBox>
        : <div ref={containerRef} style={{ width: '100%', minHeight: height }} />
      }
    </ChartContainer>
  );
}
