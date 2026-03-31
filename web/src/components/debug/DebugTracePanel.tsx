/**
 * DebugTracePanel — Visual pipeline trace viewer.
 *
 * Shows each pipeline stage as a node in a vertical timeline:
 * - Stage name, status badge, duration
 * - Collapsible input/output data
 * - Color-coded by status (done/error/skipped)
 */

import { useState } from 'react';
import styled, { keyframes, css } from 'styled-components';
import type { DebugTrace, StageTrace } from '@/utils/types';

// ── Animations ──
const fadeIn = keyframes`
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
`;

const pulse = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
`;

// ── Status config ──
const STATUS_CONFIG: Record<string, { color: string; bg: string; icon: string; label: string }> = {
  done:        { color: '#52c41a', bg: '#f6ffed', icon: '✓', label: 'Done' },
  error:       { color: '#ff4d4f', bg: '#fff2f0', icon: '✗', label: 'Error' },
  skipped:     { color: '#faad14', bg: '#fffbe6', icon: '⊘', label: 'Skipped' },
  running:     { color: '#4B6BFB', bg: '#f0f5ff', icon: '◎', label: 'Running' },
  pending:     { color: '#8c8c8c', bg: '#fafafa', icon: '○', label: 'Pending' },
  interrupted: { color: '#fa8c16', bg: '#fff7e6', icon: '⚠', label: 'Interrupted' },
};

// ── Styled Components ──
const PanelWrapper = styled.div`
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 16px;
  margin-top: 12px;
  animation: ${fadeIn} 0.3s ease;
`;

const PanelHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
`;

const PanelTitle = styled.div`
  font-size: 13px;
  font-weight: 600;
  color: #262626;
  display: flex;
  align-items: center;
  gap: 8px;
`;

const HeaderBadge = styled.span`
  font-size: 11px;
  font-weight: 500;
  color: #8c8c8c;
  background: #f0f0f0;
  padding: 2px 8px;
  border-radius: 10px;
`;

const DurationBadge = styled.span`
  font-size: 11px;
  font-weight: 500;
  color: #4B6BFB;
  background: #f0f5ff;
  padding: 2px 8px;
  border-radius: 10px;
`;

const Timeline = styled.div`
  position: relative;
  padding-left: 24px;

  &::before {
    content: '';
    position: absolute;
    left: 7px;
    top: 4px;
    bottom: 4px;
    width: 2px;
    background: #e8e8e8;
    border-radius: 1px;
  }
`;

const StageNode = styled.div<{ $index: number }>`
  position: relative;
  margin-bottom: 4px;
  animation: ${fadeIn} 0.2s ease;
  animation-delay: ${p => p.$index * 0.03}s;
  animation-fill-mode: both;
`;

const StageDot = styled.div<{ $color: string; $isActive: boolean }>`
  position: absolute;
  left: -24px;
  top: 10px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: ${p => p.$color};
  border: 2px solid white;
  box-shadow: 0 0 0 2px ${p => p.$color}33;
  z-index: 1;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;

  ${p => p.$isActive && css`
    transform: scale(1.2);
    box-shadow: 0 0 0 4px ${p.$color}44;
  `}
`;

const StageCard = styled.div<{ $statusBg: string; $expanded: boolean }>`
  background: white;
  border: 1px solid ${p => p.$expanded ? '#d9d9d9' : '#f0f0f0'};
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  overflow: hidden;

  &:hover {
    border-color: #d9d9d9;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  }
`;

const StageHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  gap: 8px;
`;

const StageName = styled.span`
  font-size: 12px;
  font-weight: 500;
  color: #262626;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const StatusTag = styled.span<{ $color: string; $bg: string }>`
  font-size: 10px;
  font-weight: 600;
  color: ${p => p.$color};
  background: ${p => p.$bg};
  padding: 1px 6px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  flex-shrink: 0;
`;

const DurationTag = styled.span`
  font-size: 11px;
  color: #8c8c8c;
  font-family: 'JetBrains Mono', monospace;
  flex-shrink: 0;
`;

const ExpandIcon = styled.span<{ $expanded: boolean }>`
  font-size: 10px;
  color: #bfbfbf;
  transition: transform 0.15s ease;
  transform: rotate(${p => p.$expanded ? 90 : 0}deg);
  flex-shrink: 0;
`;

const StageDetails = styled.div`
  border-top: 1px solid #f5f5f5;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const DataSection = styled.div``;

const DataLabel = styled.div`
  font-size: 10px;
  font-weight: 600;
  color: #8c8c8c;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
`;

const DataContent = styled.pre`
  font-size: 11px;
  line-height: 1.5;
  color: #434343;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
  padding: 8px 10px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'JetBrains Mono', monospace;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
`;

const ErrorContent = styled(DataContent)`
  background: #fff2f0;
  border-color: #ffccc7;
  color: #cf1322;
`;

const CollapseAllBtn = styled.button`
  font-size: 11px;
  color: #8c8c8c;
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: inherit;

  &:hover {
    color: #4B6BFB;
    background: #f0f5ff;
  }
`;

// ── Helper ──
function formatData(data: Record<string, any>): string {
  if (!data || Object.keys(data).length === 0) return '(empty)';
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

function formatDuration(ms: number): string {
  if (ms < 1) return '<1ms';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ── Stage Row Component ──
function StageRow({
  stage,
  index,
  expanded,
  onToggle,
}: {
  stage: StageTrace;
  index: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const cfg = STATUS_CONFIG[stage.status] || STATUS_CONFIG.pending;
  const hasInput = stage.input && Object.keys(stage.input).length > 0;
  const hasOutput = stage.output && Object.keys(stage.output).length > 0;
  const hasError = !!stage.error;
  const hasDetails = hasInput || hasOutput || hasError;

  return (
    <StageNode $index={index}>
      <StageDot $color={cfg.color} $isActive={expanded} />
      <StageCard $statusBg={cfg.bg} $expanded={expanded}>
        <StageHeader onClick={hasDetails ? onToggle : undefined} style={hasDetails ? {} : { cursor: 'default' }}>
          <StageName title={stage.stage}>{stage.stage}</StageName>
          <StatusTag $color={cfg.color} $bg={cfg.bg}>{cfg.label}</StatusTag>
          {stage.duration_ms > 0 && (
            <DurationTag>{formatDuration(stage.duration_ms)}</DurationTag>
          )}
          {hasDetails && <ExpandIcon $expanded={expanded}>▶</ExpandIcon>}
        </StageHeader>

        {expanded && hasDetails && (
          <StageDetails>
            {hasInput && (
              <DataSection>
                <DataLabel>Input</DataLabel>
                <DataContent>{formatData(stage.input)}</DataContent>
              </DataSection>
            )}
            {hasOutput && (
              <DataSection>
                <DataLabel>Output</DataLabel>
                <DataContent>{formatData(stage.output)}</DataContent>
              </DataSection>
            )}
            {hasError && (
              <DataSection>
                <DataLabel>Error</DataLabel>
                <ErrorContent>{stage.error}</ErrorContent>
              </DataSection>
            )}
          </StageDetails>
        )}
      </StageCard>
    </StageNode>
  );
}


// ── Main Panel ──
interface DebugTracePanelProps {
  trace: DebugTrace;
}

export default function DebugTracePanel({ trace }: DebugTracePanelProps) {
  const [expandedSet, setExpandedSet] = useState<Set<number>>(new Set());

  const toggle = (idx: number) => {
    setExpandedSet(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const expandAll = () => {
    setExpandedSet(new Set(trace.stages.map((_, i) => i)));
  };

  const collapseAll = () => {
    setExpandedSet(new Set());
  };

  const doneCount = trace.stages.filter(s => s.status === 'done').length;
  const errorCount = trace.stages.filter(s => s.status === 'error').length;
  const skippedCount = trace.stages.filter(s => s.status === 'skipped').length;

  return (
    <PanelWrapper>
      <PanelHeader>
        <PanelTitle>
          🔍 Pipeline Trace
          <HeaderBadge>
            {doneCount} done{errorCount > 0 ? ` · ${errorCount} error` : ''}{skippedCount > 0 ? ` · ${skippedCount} skipped` : ''}
          </HeaderBadge>
          <DurationBadge>
            {formatDuration(trace.total_duration_ms)}
          </DurationBadge>
        </PanelTitle>
        <div style={{ display: 'flex', gap: 4 }}>
          <CollapseAllBtn onClick={expandAll}>Expand All</CollapseAllBtn>
          <CollapseAllBtn onClick={collapseAll}>Collapse</CollapseAllBtn>
        </div>
      </PanelHeader>

      <Timeline>
        {trace.stages.map((stage, i) => (
          <StageRow
            key={i}
            stage={stage}
            index={i}
            expanded={expandedSet.has(i)}
            onToggle={() => toggle(i)}
          />
        ))}
      </Timeline>
    </PanelWrapper>
  );
}
