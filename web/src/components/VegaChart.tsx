/**
 * VegaChart — Renders Vega-Lite charts from JSON spec + data.
 *
 * Uses dynamic import (next/dynamic) to avoid SSR issues with vega-embed.
 */
import { useEffect, useRef, useState } from 'react';
import styled from 'styled-components';

const ChartContainer = styled.div`
  margin-top: 12px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 16px;
  background: #fafafa;
  position: relative;
  min-height: 100px;

  .vega-embed {
    width: 100%;
  }
  .vega-embed .vega-actions {
    right: 8px;
    top: 8px;
  }
`;

const ChartTitle = styled.div`
  font-size: 13px;
  font-weight: 600;
  color: #434343;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
`;

const ReasoningText = styled.div`
  font-size: 12px;
  color: #8c8c8c;
  font-style: italic;
  margin-bottom: 12px;
  line-height: 1.5;
`;

const ChartTypeBadge = styled.span`
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  color: #531dab;
  background: #f9f0ff;
  border: 1px solid #d3adf7;
  font-weight: 500;
`;

const ErrorBox = styled.div`
  color: #cf1322;
  background: #fff2f0;
  border: 1px solid #ffccc7;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 13px;
`;

interface VegaChartProps {
  spec: Record<string, any>;
  data?: Record<string, any>[];
  reasoning?: string;
  chartType?: string;
  width?: number;
  height?: number;
}

export default function VegaChart({
  spec,
  data,
  reasoning,
  chartType,
  width = 680,
  height = 360,
}: VegaChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const viewRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current || !spec || Object.keys(spec).length === 0) return;

    let cancelled = false;

    const renderChart = async () => {
      try {
        // Dynamic import to avoid SSR issues
        const vegaEmbed = (await import('vega-embed')).default;

        // Inject data into spec
        const fullSpec: any = {
          ...spec,
          width: width - 80,
          height: height - 80,
          autosize: { type: 'fit', contains: 'padding' },
        };

        // Inject data values if provided
        if (data && data.length > 0) {
          fullSpec.data = { values: data };
        }

        if (cancelled) return;

        // Clean up previous view
        if (viewRef.current) {
          viewRef.current.finalize();
          viewRef.current = null;
        }

        const result = await vegaEmbed(containerRef.current!, fullSpec, {
          mode: 'vega-lite',
          renderer: 'svg',
          tooltip: { theme: 'custom' },
          actions: {
            export: true,
            editor: false,
            source: false,
            compiled: false,
          },
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

  if (!spec || Object.keys(spec).length === 0) {
    return null;
  }

  return (
    <ChartContainer>
      <ChartTitle>
        📊 Biểu đồ
        {chartType && <ChartTypeBadge>{chartType.replace('_', ' ')}</ChartTypeBadge>}
      </ChartTitle>
      {reasoning && <ReasoningText>{reasoning}</ReasoningText>}
      {error ? (
        <ErrorBox>Chart render error: {error}</ErrorBox>
      ) : (
        <div ref={containerRef} style={{ width, minHeight: height }} />
      )}
    </ChartContainer>
  );
}
