/**
 * DebugTracePanel — Memphis-style pipeline trace viewer.
 *
 * Vertical Memphis timeline of every stage:
 * - Square dot with stage SVG icon (matches home.tsx icon set)
 * - Hard-bordered card with offset shadow per stage
 * - Sticker-style status tag (done/error/skipped/...)
 * - Click to expand → input/output JSON in black mono panel
 */

import React, { useState } from 'react';
import styled, { keyframes } from 'styled-components';
import type { DebugTrace, StageTrace } from '@/utils/types';

/* ── Animations ─────────────────────────────────────────────── */
const fadeIn = keyframes`
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
`;
const memSpin = keyframes`
  to { transform: rotate(360deg); }
`;

const SpinSvg = styled.svg`
  animation: ${memSpin} 0.9s steps(8, end) infinite;
`;

/* ── Stage SVG icon set (mirrors the one used in home.tsx) ──── */
const StageIcons: Record<string, React.ReactElement> = {
  start: (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><polygon points="7,1 3,7 6,7 5,11 9,5 6,5" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="miter" /></svg>
  ),
  '0': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1 L11 3 L11 7 C11 9.5 6 11 6 11 C6 11 1 9.5 1 7 L1 3 Z" fill="#00D4FF" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="round" /><line x1="4" y1="6" x2="5.5" y2="8" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square" /><line x1="5.5" y1="8" x2="8" y2="4.5" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square" /></svg>
  ),
  '0.5': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="10" height="7" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1.2" /><polygon points="3,8 3,11 6,8" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1" strokeLinejoin="miter" /><line x1="3" y1="4" x2="9" y2="4" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square" /><line x1="3" y1="6" x2="7" y2="6" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square" /></svg>
  ),
  '0.7': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="2" width="4" height="3" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" /><rect x="7" y="7" width="4" height="3" fill="#00D4FF" stroke="#0D0D0D" strokeWidth="1.2" /><line x1="5" y1="3.5" x2="7" y2="8.5" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square" /><polygon points="6.5,8 7.5,9 6.5,9.5" fill="#0D0D0D" /></svg>
  ),
  '1': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><polygon points="1,2 11,2 7,6 7,10 5,10 5,6" fill="#FF6B35" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="miter" /></svg>
  ),
  '2': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="9" height="10" fill="#7B2FFF" stroke="#0D0D0D" strokeWidth="1.2" /><rect x="3" y="3" width="5" height="1.2" fill="#FAFAF5" /><rect x="3" y="5.5" width="5" height="1.2" fill="#FAFAF5" /><rect x="3" y="8" width="3.5" height="1.2" fill="#FAFAF5" /></svg>
  ),
  '3': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><ellipse cx="6" cy="6" rx="5" ry="4" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" /><line x1="4" y1="4" x2="4" y2="8" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square" /><line x1="6" y1="3" x2="6" y2="9" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square" /><line x1="8" y1="4" x2="8" y2="8" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square" /></svg>
  ),
  '4': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="5" fill="none" stroke="#0D0D0D" strokeWidth="1.2" /><circle cx="6" cy="6" r="3" fill="none" stroke="#0D0D0D" strokeWidth="1.2" /><circle cx="6" cy="6" r="1.5" fill="#FF3366" /></svg>
  ),
  '5': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="5" cy="5" r="3.5" fill="#00E676" stroke="#0D0D0D" strokeWidth="1.2" /><line x1="8" y1="8" x2="11" y2="11" stroke="#0D0D0D" strokeWidth="1.8" strokeLinecap="square" /></svg>
  ),
  '6': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="4" width="5" height="3" rx="1.5" fill="none" stroke="#0D0D0D" strokeWidth="1.3" /><rect x="6" y="5" width="5" height="3" rx="1.5" fill="none" stroke="#0D0D0D" strokeWidth="1.3" /><line x1="5" y1="5.5" x2="7" y2="6.5" stroke="#0D0D0D" strokeWidth="1" /><rect x="1" y="4" width="5" height="3" rx="1.5" fill="#00D4FF" opacity="0.6" stroke="none" /><rect x="6" y="5" width="5" height="3" rx="1.5" fill="#FF3366" opacity="0.6" stroke="none" /></svg>
  ),
  '7': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="3" cy="4" r="2" fill="none" stroke="#0D0D0D" strokeWidth="1.2" /><circle cx="3" cy="8" r="2" fill="none" stroke="#0D0D0D" strokeWidth="1.2" /><line x1="5" y1="5" x2="11" y2="2" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square" /><line x1="5" y1="7" x2="11" y2="10" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square" /><circle cx="3" cy="4" r="1" fill="#FF6B35" /><circle cx="3" cy="8" r="1" fill="#FF6B35" /></svg>
  ),
  '8': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><ellipse cx="6" cy="3" rx="4.5" ry="2" fill="#C6FF00" stroke="#0D0D0D" strokeWidth="1.2" /><path d="M1.5 3 L1.5 9 C1.5 10.1 3.5 11 6 11 C8.5 11 10.5 10.1 10.5 9 L10.5 3" fill="none" stroke="#0D0D0D" strokeWidth="1.2" /><ellipse cx="6" cy="6" rx="4.5" ry="2" fill="none" stroke="#0D0D0D" strokeWidth="1" strokeDasharray="2,2" /></svg>
  ),
  '9': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="2" y="1" width="8" height="10" fill="#7B2FFF" stroke="#0D0D0D" strokeWidth="1.2" /><rect x="2" y="1" width="2" height="10" fill="#0D0D0D" /><line x1="5" y1="4" x2="9" y2="4" stroke="#FAFAF5" strokeWidth="1" /><line x1="5" y1="6" x2="9" y2="6" stroke="#FAFAF5" strokeWidth="1" /><line x1="5" y1="8" x2="7.5" y2="8" stroke="#FAFAF5" strokeWidth="1" /></svg>
  ),
  '10': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="5" fill="#00BFA5" stroke="#0D0D0D" strokeWidth="1.2" /><polyline points="6,3 6,6 8.5,8" fill="none" stroke="#0D0D0D" strokeWidth="1.3" strokeLinecap="square" /></svg>
  ),
  '11': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="8" width="3" height="3" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1" /><rect x="4.5" y="5" width="3" height="6" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1" /><rect x="8" y="2" width="3" height="9" fill="#00D4FF" stroke="#0D0D0D" strokeWidth="1" /></svg>
  ),
  '12': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><polygon points="7,1 2.5,7 5.5,7 5,11 9.5,5 6.5,5" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="miter" /></svg>
  ),
  '13': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="10" height="10" fill="#00E676" stroke="#0D0D0D" strokeWidth="1.2" /><polyline points="3,6 5,8.5 9,3.5" fill="none" stroke="#0D0D0D" strokeWidth="1.8" strokeLinecap="square" strokeLinejoin="miter" /></svg>
  ),
  '13.5': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="10" height="10" fill="#00E676" stroke="#0D0D0D" strokeWidth="1.2" /><polyline points="3,6 5,8.5 9,3.5" fill="none" stroke="#0D0D0D" strokeWidth="1.8" strokeLinecap="square" strokeLinejoin="miter" /></svg>
  ),
  '14': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="10" height="10" fill="#00E676" stroke="#0D0D0D" strokeWidth="1.2" /><polyline points="3,6 5,8.5 9,3.5" fill="none" stroke="#0D0D0D" strokeWidth="1.8" strokeLinecap="square" strokeLinejoin="miter" /></svg>
  ),
};

/** Extract "0" / "0.5" / "13.5" from "Stage 0.5: ConversationContext" or similar */
function getStageId(stageStr: string): string {
  const m = stageStr.match(/(\d+(?:\.\d+)?)/);
  return m ? m[1] : 'start';
}

const getStageIcon = (stageStr: string): React.ReactElement =>
  StageIcons[getStageId(stageStr)] ?? StageIcons['12'];

/* ── Status config (Memphis colors) ─────────────────────────── */
const STATUS_CONFIG: Record<string, { fg: string; bg: string; label: string; icon: React.ReactElement }> = {
  done: {
    fg: '#0D0D0D', bg: '#00E676', label: 'Done',
    icon: <svg width="10" height="10" viewBox="0 0 12 12" fill="none"><polyline points="2,6 5,9 10,3" stroke="#0D0D0D" strokeWidth="2" strokeLinecap="square" strokeLinejoin="miter" fill="none" /></svg>,
  },
  error: {
    fg: '#fff', bg: '#FF1744', label: 'Error',
    icon: <svg width="10" height="10" viewBox="0 0 12 12" fill="none"><line x1="2" y1="2" x2="10" y2="10" stroke="#fff" strokeWidth="2" strokeLinecap="square" /><line x1="10" y1="2" x2="2" y2="10" stroke="#fff" strokeWidth="2" strokeLinecap="square" /></svg>,
  },
  skipped: {
    fg: '#0D0D0D', bg: '#FF6B35', label: 'Skipped',
    icon: <svg width="10" height="10" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4" stroke="#0D0D0D" strokeWidth="1.5" fill="none" /><line x1="3" y1="9" x2="9" y2="3" stroke="#0D0D0D" strokeWidth="1.5" strokeLinecap="square" /></svg>,
  },
  running: {
    fg: '#0D0D0D', bg: '#00D4FF', label: 'Running',
    icon: <SpinSvg width="10" height="10" viewBox="0 0 12 12" fill="none"><rect x="5" y="1" width="2" height="3" fill="#0D0D0D" /><rect x="5" y="8" width="2" height="3" fill="#0D0D0D" opacity="0.4" /><rect x="1" y="5" width="3" height="2" fill="#0D0D0D" opacity="0.6" /><rect x="8" y="5" width="3" height="2" fill="#0D0D0D" opacity="0.4" /></SpinSvg>,
  },
  pending: {
    fg: '#0D0D0D', bg: '#E2E0D8', label: 'Pending',
    icon: <svg width="10" height="10" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4" stroke="#0D0D0D" strokeWidth="1.5" fill="none" /></svg>,
  },
  interrupted: {
    fg: '#0D0D0D', bg: '#FFE600', label: 'Interrupted',
    icon: <svg width="10" height="10" viewBox="0 0 12 12" fill="none"><polygon points="6,1 11,11 1,11" stroke="#0D0D0D" strokeWidth="1.5" fill="none" strokeLinejoin="miter" /><line x1="6" y1="5" x2="6" y2="8" stroke="#0D0D0D" strokeWidth="1.5" strokeLinecap="square" /><rect x="5.4" y="9" width="1.2" height="1.2" fill="#0D0D0D" /></svg>,
  },
};

/* ── Styled components — Memphis ─────────────────────────────── */
const PanelWrapper = styled.div`
  background: var(--m-bg);
  border: 2.5px solid var(--m-black);
  box-shadow: 5px 5px 0 var(--m-black);
  padding: 14px 14px 12px;
  margin-top: 4px;
  font-family: 'Space Grotesk', sans-serif;
  position: relative;
  animation: ${fadeIn} 0.25s ease;

  /* Top diagonal stripe ribbon */
  &::before {
    content: '';
    position: absolute;
    top: -5px; left: 0; right: 0;
    height: 5px;
    background: repeating-linear-gradient(
      45deg,
      var(--m-pink) 0 12px,
      var(--m-yellow) 12px 24px,
      var(--m-cyan) 24px 36px
    );
  }

  /* Top-right "TRACE" stamp */
  &::after {
    content: 'TRACE';
    position: absolute;
    top: -13px; right: 14px;
    background: var(--m-black);
    color: var(--m-yellow);
    padding: 2px 8px;
    font-size: 9px;
    font-weight: 900;
    letter-spacing: 1.8px;
    border: 2px solid var(--m-black);
    box-shadow: 2px 2px 0 var(--m-pink);
    transform: rotate(2deg);
  }
`;

const PanelHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding-bottom: 10px;
  margin-bottom: 12px;
  border-bottom: 1.5px dashed var(--m-black);
`;

const PanelTitle = styled.div`
  font-size: 12px;
  font-weight: 900;
  color: var(--m-black);
  display: flex;
  align-items: center;
  gap: 8px;
  text-transform: uppercase;
  letter-spacing: 1px;
`;

const TitleIcon = styled.span`
  display: inline-flex;
  width: 22px; height: 22px;
  background: var(--m-cyan);
  border: 2px solid var(--m-black);
  box-shadow: 2px 2px 0 var(--m-black);
  align-items: center; justify-content: center;
`;

const StickerBadge = styled.span<{ $bg?: string; $color?: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: ${p => p.$bg || 'var(--m-bg-2)'};
  color: ${p => p.$color || 'var(--m-black)'};
  border: 1.5px solid var(--m-black);
  box-shadow: 2px 2px 0 var(--m-black);
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.6px;
`;

const ToolbarRight = styled.div`
  margin-left: auto;
  display: flex;
  gap: 4px;
`;

const ToolbarBtn = styled.button`
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--m-black);
  background: white;
  border: 1.5px solid var(--m-black);
  box-shadow: 2px 2px 0 var(--m-black);
  padding: 3px 8px;
  cursor: pointer;
  transition: transform 0.08s, box-shadow 0.08s, background 0.12s;

  &:hover {
    background: var(--m-yellow);
    transform: translate(-1px, -1px);
    box-shadow: 3px 3px 0 var(--m-black);
  }
  &:active {
    transform: translate(2px, 2px);
    box-shadow: none;
  }
`;

const Timeline = styled.div`
  position: relative;
  padding-left: 32px;

  /* Dotted Memphis vertical rail */
  &::before {
    content: '';
    position: absolute;
    left: 11px;
    top: 8px;
    bottom: 8px;
    width: 2px;
    background-image: repeating-linear-gradient(
      to bottom,
      var(--m-black) 0 4px,
      transparent 4px 8px
    );
  }
`;

const StageNode = styled.div<{ $index: number }>`
  position: relative;
  margin-bottom: 8px;
  animation: ${fadeIn} 0.2s ease;
  animation-delay: ${p => p.$index * 0.025}s;
  animation-fill-mode: both;
`;

const StageDot = styled.div<{ $bg: string; $isActive: boolean }>`
  position: absolute;
  left: -32px;
  top: 6px;
  width: 24px;
  height: 24px;
  background: ${p => p.$bg};
  border: 2px solid var(--m-black);
  box-shadow: 2px 2px 0 var(--m-black);
  display: flex; align-items: center; justify-content: center;
  z-index: 1;
  transition: transform 0.15s ease;
  transform: ${p => p.$isActive ? 'translate(-1px, -1px) rotate(-3deg)' : 'none'};
`;

const StageCard = styled.div<{ $expanded: boolean }>`
  background: white;
  border: 2px solid var(--m-black);
  box-shadow: ${p => p.$expanded ? '4px 4px 0 var(--m-black)' : '3px 3px 0 var(--m-black)'};
  cursor: pointer;
  transition: box-shadow 0.12s ease, transform 0.12s ease;

  &:hover {
    transform: translate(-1px, -1px);
    box-shadow: 4px 4px 0 var(--m-black);
  }
`;

const StageHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
`;

const StageName = styled.span`
  font-size: 12px;
  font-weight: 800;
  color: var(--m-black);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-transform: uppercase;
  letter-spacing: 0.4px;
`;

const StatusTag = styled.span<{ $fg: string; $bg: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 9.5px;
  font-weight: 900;
  color: ${p => p.$fg};
  background: ${p => p.$bg};
  padding: 2px 7px;
  border: 1.5px solid var(--m-black);
  box-shadow: 1.5px 1.5px 0 var(--m-black);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  flex-shrink: 0;
`;

const DurationTag = styled.span`
  font-size: 10.5px;
  font-weight: 700;
  color: #555;
  font-family: 'JetBrains Mono', monospace;
  flex-shrink: 0;

  &::before { content: '['; color: var(--m-pink); margin-right: 2px; }
  &::after  { content: ']'; color: var(--m-pink); margin-left: 2px; }
`;

const ExpandIcon = styled.span<{ $expanded: boolean }>`
  display: inline-flex;
  width: 14px; height: 14px;
  background: ${p => p.$expanded ? 'var(--m-yellow)' : 'white'};
  border: 1.5px solid var(--m-black);
  align-items: center; justify-content: center;
  transition: transform 0.15s ease, background 0.15s;
  transform: rotate(${p => p.$expanded ? 90 : 0}deg);
  flex-shrink: 0;

  &::before {
    content: '';
    width: 0; height: 0;
    border-left: 5px solid var(--m-black);
    border-top: 3px solid transparent;
    border-bottom: 3px solid transparent;
    margin-left: 1px;
  }
`;

const StageDetails = styled.div`
  border-top: 1.5px dashed var(--m-black);
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--m-bg);
`;

const DataLabel = styled.div`
  font-size: 9.5px;
  font-weight: 900;
  color: var(--m-black);
  text-transform: uppercase;
  letter-spacing: 1.2px;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 6px;

  &::before {
    content: '';
    width: 8px; height: 8px;
    background: var(--m-pink);
    border: 1.2px solid var(--m-black);
    display: inline-block;
  }
`;

const DataContent = styled.pre`
  font-size: 11px;
  line-height: 1.55;
  color: #E8E6E0;
  background: #0f0f0f;
  border: 2px solid var(--m-black);
  box-shadow: 3px 3px 0 var(--m-cyan);
  padding: 8px 10px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'JetBrains Mono', monospace;
  max-height: 220px;
  overflow-y: auto;
  margin: 0;
`;

const ErrorContent = styled(DataContent)`
  background: #2a0810;
  color: #ffb4c0;
  box-shadow: 3px 3px 0 var(--m-red);
`;

/* ── Helpers ────────────────────────────────────────────────── */
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

/* ── Stage row ──────────────────────────────────────────────── */
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

  const dotBg =
    stage.status === 'done'    ? 'var(--m-green)'
    : stage.status === 'error' ? 'var(--m-red)'
    : stage.status === 'skipped' ? 'var(--m-orange)'
    : stage.status === 'running' ? 'var(--m-cyan)'
    : 'var(--m-bg-2)';

  return (
    <StageNode $index={index}>
      <StageDot $bg={dotBg} $isActive={expanded}>
        {getStageIcon(stage.stage)}
      </StageDot>
      <StageCard $expanded={expanded}>
        <StageHeader onClick={hasDetails ? onToggle : undefined} style={hasDetails ? {} : { cursor: 'default' }}>
          <StageName title={stage.stage}>{stage.stage}</StageName>
          <StatusTag $fg={cfg.fg} $bg={cfg.bg}>
            {cfg.icon}
            {cfg.label}
          </StatusTag>
          {stage.duration_ms > 0 && (
            <DurationTag>{formatDuration(stage.duration_ms)}</DurationTag>
          )}
          {hasDetails && <ExpandIcon $expanded={expanded} />}
        </StageHeader>

        {expanded && hasDetails && (
          <StageDetails>
            {hasInput && (
              <div>
                <DataLabel>Input</DataLabel>
                <DataContent>{formatData(stage.input)}</DataContent>
              </div>
            )}
            {hasOutput && (
              <div>
                <DataLabel>Output</DataLabel>
                <DataContent>{formatData(stage.output)}</DataContent>
              </div>
            )}
            {hasError && (
              <div>
                <DataLabel>Error</DataLabel>
                <ErrorContent>{stage.error}</ErrorContent>
              </div>
            )}
          </StageDetails>
        )}
      </StageCard>
    </StageNode>
  );
}

/* ── Main panel ─────────────────────────────────────────────── */
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
  const expandAll = () => setExpandedSet(new Set(trace.stages.map((_, i) => i)));
  const collapseAll = () => setExpandedSet(new Set());

  const doneCount    = trace.stages.filter(s => s.status === 'done').length;
  const errorCount   = trace.stages.filter(s => s.status === 'error').length;
  const skippedCount = trace.stages.filter(s => s.status === 'skipped').length;

  return (
    <PanelWrapper>
      <PanelHeader>
        <PanelTitle>
          <TitleIcon>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="5" cy="5" r="3.5" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" /><line x1="8" y1="8" x2="11" y2="11" stroke="#0D0D0D" strokeWidth="1.8" strokeLinecap="square" /></svg>
          </TitleIcon>
          Pipeline Trace
        </PanelTitle>
        <StickerBadge $bg="var(--m-yellow)">
          {doneCount} done
          {errorCount > 0   && ` · ${errorCount} err`}
          {skippedCount > 0 && ` · ${skippedCount} skip`}
        </StickerBadge>
        <StickerBadge $bg="var(--m-pink)" $color="white">
          {formatDuration(trace.total_duration_ms)}
        </StickerBadge>
        <ToolbarRight>
          <ToolbarBtn onClick={expandAll}>Expand</ToolbarBtn>
          <ToolbarBtn onClick={collapseAll}>Collapse</ToolbarBtn>
        </ToolbarRight>
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
