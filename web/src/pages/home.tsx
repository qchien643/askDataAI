import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import Head from 'next/head';
import styled, { keyframes } from 'styled-components';
import { Input, Button, Table, Tooltip, message } from 'antd';
import SiderLayout from '@/components/layouts/SiderLayout';
import RequireConnection from '@/components/guards/RequireConnection';
import DebugTracePanel from '@/components/debug/DebugTracePanel';
import VegaChart from '@/components/VegaChart';
import { api } from '@/hooks/useApi';
import type { ProgressEvent, TokenEvent } from '@/hooks/useApi';
import { useChat } from '@/contexts/ChatContext';
import type { Msg, Thread } from '@/contexts/ChatContext';
import type { DebugTrace } from '@/utils/types';

/* ═══════════════════════════════════════════════
   MEMPHIS SVG ICON COMPONENTS — no external deps
   Bold geometry, black borders, Memphis palette
   ═══════════════════════════════════════════════ */
const IconSend = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
    <polygon points="2,2 14,8 2,14 5,8" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.5" strokeLinejoin="miter" />
    <line x1="5" y1="8" x2="13" y2="8" stroke="#0D0D0D" strokeWidth="1.5" strokeLinecap="square" />
  </svg>
);
const IconLoading = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"
    style={{ animation: 'memSpin 0.8s steps(8,end) infinite' }}>
    <style>{`@keyframes memSpin { to { transform: rotate(360deg); } }`}</style>
    <rect x="7" y="1" width="2" height="4" fill="#FF3366" />
    <rect x="7" y="11" width="2" height="4" opacity="0.25" fill="#FF3366" />
    <rect x="1" y="7" width="4" height="2" opacity="0.5" fill="#FF3366" />
    <rect x="11" y="7" width="4" height="2" opacity="0.25" fill="#FF3366" />
    <rect x="3" y="3" width="2" height="2" opacity="0.75" fill="#FF3366" transform="rotate(45 4 4)" />
    <rect x="11" y="3" width="2" height="2" opacity="0.4" fill="#FF3366" transform="rotate(45 12 4)" />
  </svg>
);
const IconBug = ({ active }: { active: boolean }) => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="1" y="1" width="12" height="12"
      fill={active ? '#FF3366' : 'none'}
      stroke={active ? '#FF3366' : '#888'} strokeWidth="1.5" />
    <line x1="4" y1="4" x2="10" y2="10" stroke={active ? '#FAFAF5' : '#888'} strokeWidth="1.5" strokeLinecap="square" />
    <line x1="10" y1="4" x2="4" y2="10" stroke={active ? '#FAFAF5' : '#888'} strokeWidth="1.5" strokeLinecap="square" />
  </svg>
);
const IconChart = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="1" y="8" width="3" height="5" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1.2" />
    <rect x="5.5" y="5" width="3" height="8" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" />
    <rect x="10" y="2" width="3" height="11" fill="#00D4FF" stroke="#0D0D0D" strokeWidth="1.2" />
    <line x1="1" y1="13" x2="13" y2="13" stroke="#0D0D0D" strokeWidth="1.5" strokeLinecap="square" />
  </svg>
);
/* Memphis lightbulb — for Chain-of-Thought */
const IconThought = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M9 2 C5.7 2 3.5 4.3 3.5 7 C3.5 8.6 4.4 10 5.6 10.8 L5.6 12.5 L12.4 12.5 L12.4 10.8 C13.6 10 14.5 8.6 14.5 7 C14.5 4.3 12.3 2 9 2 Z"
      fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.6" strokeLinejoin="miter"
    />
    <rect x="6" y="13" width="6" height="1.6" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1.2" />
    <rect x="7" y="15" width="4" height="1.4" fill="#0D0D0D" />
    <line x1="1" y1="7" x2="2.4" y2="7" stroke="#0D0D0D" strokeWidth="1.5" strokeLinecap="square" />
    <line x1="15.6" y1="7" x2="17" y2="7" stroke="#0D0D0D" strokeWidth="1.5" strokeLinecap="square" />
    <line x1="2.6" y1="2.6" x2="3.6" y2="3.6" stroke="#0D0D0D" strokeWidth="1.5" strokeLinecap="square" />
    <line x1="14.4" y1="2.6" x2="15.4" y2="3.6" stroke="#0D0D0D" strokeWidth="1.5" strokeLinecap="square" />
  </svg>
);
/* Memphis lightning bolt — for SQL Generation */
const IconBolt = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
    <polygon
      points="10,1 3,9.5 8,9.5 7,17 14,7.5 9,7.5 11,1"
      fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.6" strokeLinejoin="miter"
    />
    <circle cx="2" cy="3" r="1.2" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1" />
    <rect x="14" y="13" width="2.5" height="2.5" fill="#00D4FF" stroke="#0D0D0D" strokeWidth="1" />
  </svg>
);

/* ── Stage icon map — Memphis SVG per pipeline stage ─────────────────────
   Each icon: 16×16 viewBox, bold 1.5px stroke, distinct Memphis color fill
   ──────────────────────────────────────────────────────────────────────── */
const StageIcons: Record<string, JSX.Element> = {
  /* start — lightning bolt */
  start: (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><polygon points="7,1 3,7 6,7 5,11 9,5 6,5" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="miter" /></svg>
  ),
  /* 0 — shield/guard */
  '0': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1 L11 3 L11 7 C11 9.5 6 11 6 11 C6 11 1 9.5 1 7 L1 3 Z" fill="#00D4FF" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="round" /><line x1="4" y1="6" x2="5.5" y2="8" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square" /><line x1="5.5" y1="8" x2="8" y2="4.5" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square" /></svg>
  ),
  /* 0.5 — speech bubble */
  '0.5': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="10" height="7" rx="0" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1.2" /><polygon points="3,8 3,11 6,8" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1" strokeLinejoin="miter" /><line x1="3" y1="4" x2="9" y2="4" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square" /><line x1="3" y1="6" x2="7" y2="6" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square" /></svg>
  ),
  /* 1 — funnel / classify */
  '1': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><polygon points="1,2 11,2 7,6 7,10 5,10 5,6" fill="#FF6B35" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="miter" /></svg>
  ),
  /* 2 — book / rules */
  '2': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="9" height="10" fill="#7B2FFF" stroke="#0D0D0D" strokeWidth="1.2" /><rect x="3" y="3" width="5" height="1.2" fill="#FAFAF5" /><rect x="3" y="5.5" width="5" height="1.2" fill="#FAFAF5" /><rect x="3" y="8" width="3.5" height="1.2" fill="#FAFAF5" /></svg>
  ),
  /* 3 — brain/analyze */
  '3': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><ellipse cx="6" cy="6" rx="5" ry="4" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" /><line x1="4" y1="4" x2="4" y2="8" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square" /><line x1="6" y1="3" x2="6" y2="9" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square" /><line x1="8" y1="4" x2="8" y2="8" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square" /></svg>
  ),
  /* 4 — target/sub-intent */
  '4': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="5" fill="none" stroke="#0D0D0D" strokeWidth="1.2" /><circle cx="6" cy="6" r="3" fill="none" stroke="#0D0D0D" strokeWidth="1.2" /><circle cx="6" cy="6" r="1.5" fill="#FF3366" /></svg>
  ),
  /* 5 — magnify/search */
  '5': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="5" cy="5" r="3.5" fill="#00E676" stroke="#0D0D0D" strokeWidth="1.2" /><line x1="8" y1="8" x2="11" y2="11" stroke="#0D0D0D" strokeWidth="1.8" strokeLinecap="square" /></svg>
  ),
  /* 6 — chain links */
  '6': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="4" width="5" height="3" rx="1.5" fill="none" stroke="#0D0D0D" strokeWidth="1.3" /><rect x="6" y="5" width="5" height="3" rx="1.5" fill="none" stroke="#0D0D0D" strokeWidth="1.3" /><line x1="5" y1="5.5" x2="7" y2="6.5" stroke="#0D0D0D" strokeWidth="1" /><rect x="1" y="4" width="5" height="3" rx="1.5" fill="#00D4FF" opacity="0.6" stroke="none" /><rect x="6" y="5" width="5" height="3" rx="1.5" fill="#FF3366" opacity="0.6" stroke="none" /></svg>
  ),
  /* 7 — scissors/prune */
  '7': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="3" cy="4" r="2" fill="none" stroke="#0D0D0D" strokeWidth="1.2" /><circle cx="3" cy="8" r="2" fill="none" stroke="#0D0D0D" strokeWidth="1.2" /><line x1="5" y1="5" x2="11" y2="2" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square" /><line x1="5" y1="7" x2="11" y2="10" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square" /><circle cx="3" cy="4" r="1" fill="#FF6B35" /><circle cx="3" cy="8" r="1" fill="#FF6B35" /></svg>
  ),
  /* 8 — database/DDL */
  '8': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><ellipse cx="6" cy="3" rx="4.5" ry="2" fill="#C6FF00" stroke="#0D0D0D" strokeWidth="1.2" /><path d="M1.5 3 L1.5 9 C1.5 10.1 3.5 11 6 11 C8.5 11 10.5 10.1 10.5 9 L10.5 3" fill="none" stroke="#0D0D0D" strokeWidth="1.2" /><ellipse cx="6" cy="6" rx="4.5" ry="2" fill="none" stroke="#0D0D0D" strokeWidth="1" strokeDasharray="2,2" /></svg>
  ),
  /* 9 — dictionary */
  '9': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="2" y="1" width="8" height="10" fill="#7B2FFF" stroke="#0D0D0D" strokeWidth="1.2" /><rect x="2" y="1" width="2" height="10" fill="#0D0D0D" /><line x1="5" y1="4" x2="9" y2="4" stroke="#FAFAF5" strokeWidth="1" /><line x1="5" y1="6" x2="9" y2="6" stroke="#FAFAF5" strokeWidth="1" /><line x1="5" y1="8" x2="7.5" y2="8" stroke="#FAFAF5" strokeWidth="1" /></svg>
  ),
  /* 10 — memory/history */
  '10': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="5" fill="#00BFA5" stroke="#0D0D0D" strokeWidth="1.2" /><polyline points="6,3 6,6 8.5,8" fill="none" stroke="#0D0D0D" strokeWidth="1.3" strokeLinecap="square" /></svg>
  ),
  /* 11 — steps/CoT */
  '11': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="8" width="3" height="3" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1" /><rect x="4.5" y="5" width="3" height="6" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1" /><rect x="8" y="2" width="3" height="9" fill="#00D4FF" stroke="#0D0D0D" strokeWidth="1" /></svg>
  ),
  /* 12 — lightning/generate */
  '12': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><polygon points="7,1 2.5,7 5.5,7 5,11 9.5,5 6.5,5" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="miter" /></svg>
  ),
  /* 13 / 13.5 / 14 — checkmark/done */
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

/** Strip leading emoji/symbols from backend label strings */
const stripEmoji = (s: string) =>
  s.replace(/^[\u{1F000}-\u{1FFFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u00A9\u00AE\u{1F004}-\u{1F0CF}\u{1F3FB}-\u{1F9FF}\u2139\u203C\u2049\u{231A}-\u{231B}\u{2328}\u{23CF}\u{23E9}-\u{23F3}\u{23F8}-\u{23FA}\u{25AA}-\u{25AB}\u{25B6}\u{25C0}\u{25FB}-\u{25FE}\u{2600}-\u{2604}\u{260E}\u{2611}\u{2614}-\u{2615}\u{2618}\u{261D}\u{2620}\u{2622}-\u{2623}\u{2626}\u{262A}\u{262E}-\u{262F}\u{2638}-\u{263A}\u{2640}\u{2642}\u{2648}-\u{2653}\u{265F}-\u{2660}\u{2663}\u{2665}-\u{2666}\u{2668}\u{267B}\u{267E}-\u{267F}\u{2692}-\u{2697}\u{2699}\u{269B}-\u{269C}\u{26A0}-\u{26A1}\u{26AA}-\u{26AB}\u{26B0}-\u{26B1}\u{26BD}-\u{26BE}\u{26C4}-\u{26C5}\u{26CE}-\u{26CF}\u{26D1}\u{26D3}-\u{26D4}\u{26E9}-\u{26EA}\u{26F0}-\u{26F5}\u{26F7}-\u{26FA}\u{26FD}\u{2702}\u{2705}\u{2708}-\u{270D}\u{270F}\u{2712}\u{2714}\u{2716}\u{271D}\u{2721}\u{2728}\u{2733}-\u{2734}\u{2744}\u{2747}\u{274C}\u{274E}\u{2753}-\u{2755}\u{2757}\u{2763}-\u{2764}\u{2795}-\u{2797}\u{27A1}\u{27B0}\u{27BF}\u{2934}-\u{2935}\u{2B05}-\u{2B07}\u{2B1B}-\u{2B1C}\u{2B50}\u{2B55}\u{3030}\u{303D}\u{3297}\u{3299}⏳✅❌🛡️💭🔍📋🧠🎯📊🔗✂️🏗️📖💾🧩⚡??\s]+/u, '').trim();

/** Get the Memphis SVG icon for a given stage id */
const getStageIcon = (stage: string): JSX.Element =>
  StageIcons[stage] ?? StageIcons['12'];

/* ── SQL syntax highlighter (token-based, no external dep) ───────────── */
const SQL_KW = new Set(
  ('SELECT FROM WHERE JOIN INNER LEFT RIGHT FULL OUTER CROSS ON GROUP BY ' +
    'ORDER AS HAVING LIMIT OFFSET TOP DISTINCT UNION ALL AND OR NOT IN IS ' +
    'NULL LIKE BETWEEN CASE WHEN THEN ELSE END WITH OVER PARTITION ASC DESC ' +
    'EXISTS VALUES INSERT INTO UPDATE DELETE SET CREATE TABLE VIEW DROP ALTER').split(' ')
);
const SQL_FN = new Set(
  ('COUNT SUM AVG MIN MAX CAST CONVERT YEAR MONTH DAY DATE GETDATE ROUND ABS ' +
    'COALESCE ISNULL LEN UPPER LOWER LTRIM RTRIM TRIM SUBSTRING REPLACE FORMAT ' +
    'DATEADD DATEDIFF DATEPART ROW_NUMBER RANK DENSE_RANK NTILE LAG LEAD').split(' ')
);

function highlightSql(sql: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < sql.length) {
    const ch = sql[i];
    // line comment
    if (ch === '-' && sql[i + 1] === '-') {
      const end = sql.indexOf('\n', i);
      const stop = end === -1 ? sql.length : end;
      out.push(<span key={key++} className="cmt">{sql.slice(i, stop)}</span>);
      i = stop;
      continue;
    }
    // string
    if (ch === "'" || ch === '"') {
      const q = ch;
      let j = i + 1;
      while (j < sql.length && sql[j] !== q) j++;
      out.push(<span key={key++} className="str">{sql.slice(i, j + 1)}</span>);
      i = j + 1;
      continue;
    }
    // number
    if (/\d/.test(ch)) {
      let j = i;
      while (j < sql.length && /[\d.]/.test(sql[j])) j++;
      out.push(<span key={key++} className="num">{sql.slice(i, j)}</span>);
      i = j;
      continue;
    }
    // word
    if (/[a-zA-Z_]/.test(ch)) {
      let j = i;
      while (j < sql.length && /[\w]/.test(sql[j])) j++;
      const word = sql.slice(i, j);
      const upper = word.toUpperCase();
      if (SQL_KW.has(upper)) out.push(<span key={key++} className="kw">{word}</span>);
      else if (SQL_FN.has(upper)) out.push(<span key={key++} className="fn">{word}</span>);
      else out.push(word);
      i = j;
      continue;
    }
    // punctuation/whitespace passthrough — accumulate runs of non-token chars
    let j = i;
    while (j < sql.length && !/[a-zA-Z_'\"\d]/.test(sql[j]) && !(sql[j] === '-' && sql[j + 1] === '-')) j++;
    if (j === i) j = i + 1;
    out.push(sql.slice(i, j));
    i = j;
  }
  return out;
}


const blink = keyframes`
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
`;
const slideInLeft = keyframes`
  from { opacity: 0; transform: translateX(-16px); }
  to   { opacity: 1; transform: translateX(0); }
`;
const slideInRight = keyframes`
  from { opacity: 0; transform: translateX(16px); }
  to   { opacity: 1; transform: translateX(0); }
`;
const popIn = keyframes`
  from { opacity: 0; transform: scale(0.92) translateY(8px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
`;
const floatShape = keyframes`
  0%, 100% { transform: translateY(0) rotate(0deg); }
  50%       { transform: translateY(-10px) rotate(5deg); }
`;

const shimmer = keyframes`
  0%, 100% { opacity: 0.6; }
  50%       { opacity: 1; }
`;

const progressBar = keyframes`
  0%   { width: 0%; }
  100% { width: 100%; }
`;

const stageSlideIn = keyframes`
  from { opacity: 0; transform: translateX(-10px); }
  to   { opacity: 1; transform: translateX(0); }
`;

/* ════════════════════════════════════════════
   PIPELINE PROGRESS STYLED COMPONENTS
   ════════════════════════════════════════════ */
const stripeMove = keyframes`
  0%   { background-position: 0 0; }
  100% { background-position: 24px 0; }
`;

/* Ticket-stub frame for pipeline panel */
const ProgressPanel = styled.div`
  border: 2.5px solid var(--m-black);
  box-shadow: 6px 6px 0 var(--m-black);
  background: white;
  padding: 18px 18px 12px;
  font-family: 'Space Grotesk', sans-serif;
  margin: 18px 4px 6px 0;
  animation: ${popIn} 0.2s ease;
  max-height: 400px;
  display: flex;
  flex-direction: column;
  position: relative;

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

  /* "TICKET" stamp top-right */
  &::after {
    content: 'PIPELINE · 14 STAGES';
    position: absolute;
    top: -14px; right: 14px;
    background: var(--m-black);
    color: var(--m-yellow);
    padding: 3px 9px;
    font-size: 9px;
    font-weight: 900;
    letter-spacing: 1.8px;
    border: 2px solid var(--m-black);
    box-shadow: 2px 2px 0 var(--m-pink);
    transform: rotate(2deg);
  }
`;

const ProgressHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-shrink: 0;
  padding-bottom: 8px;
  border-bottom: 1.5px dashed var(--m-black);
`;

const ProgressTitle = styled.span`
  font-size: 11px;
  font-weight: 900;
  text-transform: uppercase;
  letter-spacing: 1.4px;
  color: var(--m-black);
`;

const PipelineTrack = styled.div`
  height: 10px;
  background: var(--m-bg-2);
  border: 2px solid var(--m-black);
  position: relative;
  overflow: hidden;
  flex-shrink: 0;
  margin-bottom: 12px;
  box-shadow: inset 0 0 0 1px white;
`;

const PipelineFill = styled.div<{ $pct: number }>`
  height: 100%;
  width: ${p => p.$pct}%;
  background-image: repeating-linear-gradient(
    -45deg,
    var(--m-pink) 0 8px,
    var(--m-yellow) 8px 16px,
    var(--m-cyan) 16px 24px
  );
  background-size: 24px 24px;
  animation: ${stripeMove} 0.8s linear infinite;
  transition: width 0.35s ease;
  border-right: ${p => p.$pct > 0 && p.$pct < 100 ? '2px solid var(--m-black)' : 'none'};
`;

/* Live timeline scroll area */
const LiveStepList = styled.div`
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0;
  &::-webkit-scrollbar { width: 3px; }
  &::-webkit-scrollbar-thumb { background: var(--m-black); }
`;

const LiveStepRow = styled.div<{ $active?: boolean; $done?: boolean }>`
  display: flex;
  gap: 10px;
  padding: 5px 0;
  animation: ${stageSlideIn} 0.22s ease;
  position: relative;

  /* vertical connector */
  &:not(:last-child)::before {
    content: '';
    position: absolute;
    left: 8px; top: 22px; bottom: 0;
    width: 1.5px;
    background: repeating-linear-gradient(
      to bottom,
      var(--m-black) 0, var(--m-black) 3px,
      transparent 3px, transparent 6px
    );
    opacity: ${p => p.$done ? 0.3 : 0.15};
  }
`;

const pulse = keyframes`
  0%, 100% { box-shadow: 0 0 0 0 rgba(255,23,68,0.5); }
  50% { box-shadow: 0 0 0 4px rgba(255,23,68,0); }
`;

const LiveDot = styled.div<{ $active?: boolean; $done?: boolean }>`
  width: 18px; height: 18px;
  border-radius: 0;
  border: 2px solid var(--m-black);
  flex-shrink: 0;
  margin-top: 1px;
  background: ${p => p.$done ? 'var(--m-cyan)' : p.$active ? 'var(--m-pink)' : 'var(--m-bg-2)'};
  box-shadow: ${p => p.$done || p.$active ? '2px 2px 0 var(--m-black)' : 'none'};
  display: flex; align-items: center; justify-content: center;
  animation: ${p => p.$active ? pulse : 'none'} 1s ease-in-out infinite;
  position: relative;
  z-index: 1;
  svg { filter: ${p => p.$done ? 'none' : p.$active ? 'brightness(0) invert(1)' : 'none'}; }
`;

const LiveContent = styled.div`
  flex: 1;
  min-width: 0;
`;

const LiveLabel = styled.div<{ $active?: boolean }>`
  font-size: 12px;
  font-weight: ${p => p.$active ? 700 : 600};
  color: ${p => p.$active ? 'var(--m-pink)' : 'var(--m-black)'};
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const LiveDetail = styled.div`
  margin-top: 2px;
  font-size: 10.5px;
  font-weight: 500;
  color: #555;
  padding: 3px 7px;
  background: var(--m-bg-2);
  border-left: 2px solid var(--m-cyan);
  word-break: break-word;
  line-height: 1.4;
`;

/* ── Streaming box (CoT / SQL) — washi tape + halftone header ── */
const StreamBox = styled.div<{ $variant: 'cot' | 'sql' }>`
  border: 2.5px solid var(--m-black);
  overflow: hidden;
  box-shadow: 5px 5px 0 var(--m-black);
  background: ${p => p.$variant === 'cot' ? '#fffde7' : '#0e0e0e'};
  height: 220px;
  display: flex;
  flex-direction: column;
  position: relative;

  /* Washi tape — top RIGHT corner so it never overlaps the title */
  &::before {
    content: '';
    position: absolute;
    top: -11px; right: 22px;
    width: 84px; height: 18px;
    background: ${p => p.$variant === 'cot' ? 'var(--m-pink)' : 'var(--m-cyan)'};
    border: 1.5px solid var(--m-black);
    transform: rotate(7deg);
    opacity: 0.92;
    z-index: 5;
  }

  /* Tape stripes */
  &::after {
    content: '';
    position: absolute;
    top: -11px; right: 22px;
    width: 84px; height: 18px;
    background-image: repeating-linear-gradient(
      90deg,
      transparent 0 6px,
      rgba(13,13,13,0.18) 6px 8px
    );
    transform: rotate(7deg);
    z-index: 6;
    pointer-events: none;
  }
`;

const StreamHead = styled.div<{ $variant: 'cot' | 'sql' }>`
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 2px solid var(--m-black);
  background: ${p => p.$variant === 'cot' ? 'var(--m-yellow)' : '#1a1a1a'};
  background-image: ${p => p.$variant === 'cot'
    ? 'radial-gradient(circle, rgba(13,13,13,0.06) 1.2px, transparent 1.2px)'
    : 'radial-gradient(circle, rgba(255,255,255,0.06) 1.2px, transparent 1.2px)'};
  background-size: 8px 8px;
  position: relative;
  z-index: 1;
`;

const StreamTitle = styled.span<{ $dark?: boolean }>`
  font-size: 10px;
  font-weight: 900;
  font-family: 'Space Grotesk', sans-serif;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: ${p => p.$dark ? '#aaa' : 'var(--m-black)'};
`;

const LiveBadge = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--m-pink);
  color: white;
  padding: 2px 7px;
  border: 1.5px solid var(--m-black);
  box-shadow: 1.5px 1.5px 0 var(--m-black);
  font-size: 9px;
  font-weight: 900;
  font-family: 'Space Grotesk', sans-serif;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  margin-left: auto;
  transform: rotate(-3deg);

  &::before {
    content: '';
    width: 6px; height: 6px;
    background: white;
    animation: ${blink} 0.8s ease-in-out infinite;
  }
`;

const StreamBody = styled.div<{ $variant: 'cot' | 'sql' }>`
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  font-family: ${p => p.$variant === 'cot' ? "'Space Grotesk', sans-serif" : "'JetBrains Mono', Consolas, monospace"};
  font-size: ${p => p.$variant === 'cot' ? '12.5px' : '11.5px'};
  line-height: 1.65;
  color: ${p => p.$variant === 'cot' ? '#1a1a1a' : '#d4d4d4'};
  white-space: pre-wrap;
  word-break: break-word;
  scroll-behavior: smooth;
  position: relative;
  z-index: 1;
`;

const StreamCursor = styled.span<{ $color: string }>`
  display: inline-block;
  width: 2px;
  height: 1em;
  background: ${p => p.$color};
  margin-left: 1px;
  vertical-align: text-bottom;
  animation: ${blink} 0.6s step-end infinite;
`;

// 14 stages total (0, 0.5, 1..13, 13.5, 14) — map to 0-100%
const STAGE_PCT: Record<string, number> = {
  start: 2,
  '0': 8,
  '0.5': 14,
  '1': 20,
  '2': 26,
  '3': 33,
  '4': 40,
  '5': 47,
  '6': 53,
  '7': 59,
  '8': 65,
  '9': 71,
  '10': 76,
  '11': 82,
  '12': 88,
  '13': 92,
  '13.5': 96,
  '14': 99,
};

/* ════════════════════════════════════════════
   THOUGHT DRAWER — ChatGPT-style reasoning panel
   ════════════════════════════════════════════ */
const drawerSlideIn = keyframes`
  from { transform: translateX(100%); opacity: 0; }
  to   { transform: translateX(0);    opacity: 1; }
`;

const ThoughtBtn = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  margin-bottom: 8px;
  background: var(--m-bg);
  border: 1.5px solid var(--m-black);
  box-shadow: 2px 2px 0 var(--m-black);
  font-family: 'Space Grotesk', sans-serif;
  font-size: 12px;
  font-weight: 700;
  color: var(--m-black);
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  transition: all 0.1s;

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

const DrawerOverlay = styled.div<{ $open: boolean }>`
  position: fixed;
  inset: 0;
  z-index: 9000;
  pointer-events: ${p => p.$open ? 'auto' : 'none'};
  background: ${p => p.$open ? 'rgba(0,0,0,0.22)' : 'transparent'};
  transition: background 0.22s;
`;

const DrawerPanel = styled.div<{ $open: boolean }>`
  position: fixed;
  top: 0; right: 0; bottom: 0;
  width: min(580px, 92vw);
  background: #fafaf8;
  border-left: 2.5px solid var(--m-black);
  box-shadow: -8px 0 0 var(--m-black);
  z-index: 9001;
  display: flex;
  flex-direction: column;
  transform: ${p => p.$open ? 'translateX(0)' : 'translateX(100%)'};
  transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
  font-family: 'Space Grotesk', sans-serif;
`;

const DrawerHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 16px;
  border-bottom: 2px solid var(--m-black);
  background: var(--m-yellow);
  flex-shrink: 0;
`;

const DrawerTitle = styled.span`
  font-size: 13px;
  font-weight: 800;
  color: var(--m-black);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  flex: 1;
`;

const DrawerClose = styled.button`
  width: 28px; height: 28px;
  background: white;
  border: 2px solid var(--m-black);
  box-shadow: 2px 2px 0 var(--m-black);
  color: var(--m-black);
  font-size: 16px;
  font-weight: 800;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  padding: 0;
  transition: all 0.1s;
  &:hover { background: var(--m-pink); transform: translate(-1px, -1px); box-shadow: 3px 3px 0 var(--m-black); }
  &:active { transform: translate(1px, 1px); box-shadow: none; }
`;

const DrawerBody = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 0;

  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-track { background: transparent; }
  &::-webkit-scrollbar-thumb { background: var(--m-black); }
`;

const ThoughtStepRow = styled.div<{ $last?: boolean }>`
  display: flex;
  gap: 12px;
  padding-bottom: ${p => p.$last ? '0' : '14px'};
  position: relative;

  /* vertical connector line */
  &:not(:last-child)::before {
    content: '';
    position: absolute;
    left: 10px; top: 24px; bottom: 0;
    width: 2px;
    background: repeating-linear-gradient(
      to bottom,
      var(--m-black) 0, var(--m-black) 4px,
      transparent 4px, transparent 8px
    );
  }
`;

const ThoughtDot = styled.div<{ $done: boolean }>`
  width: 22px; height: 22px;
  border-radius: 0;
  border: 2px solid var(--m-black);
  box-shadow: 2px 2px 0 var(--m-black);
  background: ${p => p.$done ? 'var(--m-white)' : 'var(--m-yellow)'};
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  margin-top: 0px;
  position: relative;
  z-index: 1;
`;

const ThoughtContent = styled.div`
  flex: 1;
`;

const ThoughtLabel = styled.div`
  font-size: 13px;
  font-weight: 600;
  color: var(--m-black);
  line-height: 1.4;
`;

const ThoughtDetail = styled.div`
  margin-top: 4px;
  font-size: 11.5px;
  font-weight: 500;
  color: #444;
  line-height: 1.5;
  padding: 5px 9px;
  background: var(--m-bg-2);
  border-left: 2.5px solid var(--m-cyan);
  border-radius: 0 2px 2px 0;
  word-break: break-word;
`;

const ThoughtStageId = styled.span`
  font-size: 10px;
  font-weight: 700;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-left: 6px;
`;

const DrawerFooter = styled.div`
  padding: 10px 16px;
  border-top: 2px solid var(--m-black);
  background: var(--m-bg);
  font-size: 11px;
  font-weight: 700;
  color: var(--m-black);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 6px;
`;

/* ════════════════════════════════════════════
   SIDEBAR — Memphis dark
   ════════════════════════════════════════════ */
const SidebarSection = styled.div`
  padding: 0 0 16px;
`;

/* Bold logo block at the top of the sidebar */
const SidebarLogo = styled.div`
  margin: 16px 12px 8px;
  padding: 12px 12px 12px 12px;
  background: var(--m-yellow);
  border: 2.5px solid var(--m-black);
  box-shadow: 4px 4px 0 var(--m-pink);
  display: flex;
  align-items: center;
  gap: 10px;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    top: -7px; right: -7px;
    width: 14px; height: 14px;
    background: var(--m-cyan);
    border: 2px solid var(--m-black);
    box-shadow: 1.5px 1.5px 0 var(--m-black);
    transform: rotate(-12deg);
  }
`;

const SidebarLogoMark = styled.span`
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 900;
  font-size: 22px;
  color: white;
  background: var(--m-black);
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  box-shadow: 2px 2px 0 var(--m-pink);
  border: 2px solid var(--m-black);
`;

const SidebarLogoText = styled.div`
  display: flex;
  flex-direction: column;
  line-height: 1;
  font-family: 'Space Grotesk', sans-serif;
  min-width: 0;

  & > strong {
    font-size: 13px;
    font-weight: 900;
    color: var(--m-black);
    letter-spacing: 0.8px;
    text-transform: uppercase;
  }
  & > small {
    font-size: 9px;
    font-weight: 800;
    color: var(--m-black);
    margin-top: 4px;
    letter-spacing: 1px;
    opacity: 0.7;
    text-transform: uppercase;
  }
`;

/* Section label with zigzag underline */
const SidebarLabel = styled.div`
  font-size: 10px;
  font-weight: 900;
  color: rgba(255,230,0,0.85);
  padding: 18px 16px 6px;
  text-transform: uppercase;
  letter-spacing: 1.6px;
  font-family: 'Space Grotesk', sans-serif;
  display: flex;
  align-items: center;
  gap: 10px;

  &::after {
    content: '';
    flex: 1;
    height: 6px;
    background-image:
      linear-gradient(135deg, transparent 50%, rgba(255,230,0,0.5) 50%),
      linear-gradient(45deg, transparent 50%, rgba(255,230,0,0.5) 50%);
    background-size: 6px 6px;
    background-position: 0 0, 0 3px;
    background-repeat: repeat-x;
    opacity: 0.7;
  }
`;

/* Thread items — flag-sticker style when active */
const ThreadItem = styled.button<{ $active?: boolean }>`
  width: calc(100% - 16px);
  margin: 5px 8px;
  display: block;
  text-align: left;
  padding: 10px 14px 10px 12px;
  border: 2px solid ${p => p.$active ? 'var(--m-black)' : 'rgba(255,255,255,0.10)'};
  cursor: pointer;
  background: ${p => p.$active ? 'var(--m-yellow)' : 'rgba(255,255,255,0.03)'};
  color: ${p => p.$active ? 'var(--m-black)' : 'rgba(255,255,255,0.7)'};
  font-size: 12px;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: ${p => p.$active ? 900 : 600};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  transition: all 0.12s;
  position: relative;
  box-shadow: ${p => p.$active ? '4px 4px 0 var(--m-pink)' : 'none'};

  /* Flag tail when active — triangular sticker poking right */
  &::after {
    content: '';
    position: absolute;
    right: ${p => p.$active ? '-12px' : '0'};
    top: 50%;
    transform: translateY(-50%);
    width: 0; height: 0;
    border-top: ${p => p.$active ? '12px solid transparent' : '0'};
    border-bottom: ${p => p.$active ? '12px solid transparent' : '0'};
    border-left: ${p => p.$active ? '12px solid var(--m-yellow)' : '0'};
    filter: ${p => p.$active ? 'drop-shadow(2px 0 0 var(--m-black))' : 'none'};
    pointer-events: none;
  }

  &:hover {
    background: ${p => p.$active ? 'var(--m-yellow)' : 'rgba(255,230,0,0.07)'};
    color: ${p => p.$active ? 'var(--m-black)' : 'white'};
    border-color: ${p => p.$active ? 'var(--m-black)' : 'rgba(255,230,0,0.35)'};
    transform: ${p => p.$active ? 'translate(-1px,-1px)' : 'none'};
    box-shadow: ${p => p.$active ? '5px 5px 0 var(--m-pink)' : 'none'};
  }
`;

const NewThreadBtn = styled.button`
  width: calc(100% - 16px);
  margin: 6px 8px 6px;
  padding: 10px 12px;
  border: 2px dashed var(--m-yellow);
  background: rgba(255,230,0,0.04);
  color: var(--m-yellow);
  font-size: 11px;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 900;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;

  &::before {
    content: '+';
    font-size: 14px;
    font-weight: 900;
    color: var(--m-yellow);
    background: var(--m-black);
    width: 18px; height: 18px;
    display: flex; align-items: center; justify-content: center;
    border: 1.5px solid var(--m-yellow);
  }

  &:hover {
    border-style: solid;
    background: var(--m-yellow);
    color: var(--m-black);
    box-shadow: 3px 3px 0 var(--m-pink);
    transform: translate(-1px, -1px);

    &::before {
      background: var(--m-pink);
      color: white;
      border-color: var(--m-black);
    }
  }
`;

/* ════════════════════════════════════════════
   CHAT AREA
   ════════════════════════════════════════════ */
const ChatWrapper = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
  background: var(--m-bg);

  /* Layer 1: pink dot grid */
  &::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
      radial-gradient(circle, rgba(255,51,102,0.09) 1.5px, transparent 1.5px),
      radial-gradient(circle, rgba(0,212,255,0.07)  1.5px, transparent 1.5px);
    background-size:   28px 28px, 28px 28px;
    background-position: 0 0, 14px 14px;
    pointer-events: none;
    z-index: 0;
  }

  /* Layer 2: diagonal color lines top-right corner */
  &::after {
    content: '';
    position: absolute;
    inset: 0;
    background:
      repeating-linear-gradient(
        -30deg,
        transparent,
        transparent 60px,
        rgba(255,230,0,0.04) 60px,
        rgba(255,230,0,0.04) 61px
      ),
      repeating-linear-gradient(
        60deg,
        transparent,
        transparent 80px,
        rgba(255,107,53,0.04) 80px,
        rgba(255,107,53,0.04) 81px
      );
    pointer-events: none;
    z-index: 0;
  }
`;

const MessagesArea = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 28px 24px;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 1;

  &::-webkit-scrollbar { width: 6px; }
  &::-webkit-scrollbar-thumb { background: var(--m-black); border-radius: 0; }
  &::-webkit-scrollbar-track { background: var(--m-bg-2); }
`;

const MessagesInner = styled.div`
  max-width: 820px;
  width: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
`;

/* ── User bubble — comic speech tail + sticker badge ── */
const UserBubble = styled.div`
  align-self: flex-end;
  max-width: 66%;
  background: var(--m-black);
  color: white;
  padding: 14px 20px;
  border: 2.5px solid var(--m-black);
  box-shadow: 5px 5px 0 var(--m-pink);
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 600;
  font-size: 14px;
  line-height: 1.5;
  animation: ${slideInRight} 0.2s ease;
  position: relative;
  margin: 14px 18px 0 0;

  /* Speech tail (right-bottom triangular) */
  &::after {
    content: '';
    position: absolute;
    right: -16px;
    bottom: 18px;
    width: 0; height: 0;
    border-left: 16px solid var(--m-black);
    border-top: 9px solid transparent;
    border-bottom: 9px solid transparent;
    filter: drop-shadow(2px 2px 0 var(--m-pink));
  }

  /* Yellow sticker corner accent */
  &::before {
    content: '';
    position: absolute;
    top: -5px; right: -5px;
    width: 14px; height: 14px;
    background: var(--m-yellow);
    border: 2px solid var(--m-black);
    transform: rotate(-12deg);
  }
`;

const UserBadge = styled.span`
  position: absolute;
  top: -12px; left: -10px;
  background: var(--m-yellow);
  color: var(--m-black);
  border: 2px solid var(--m-black);
  box-shadow: 2px 2px 0 var(--m-black);
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 900;
  font-size: 10px;
  letter-spacing: 1px;
  padding: 2px 8px;
  text-transform: uppercase;
  transform: rotate(-4deg);
  z-index: 2;
  white-space: nowrap;
`;

/* ── AI bubble ── */
const AiBubble = styled.div`
  align-self: flex-start;
  max-width: 92%;
  width: 100%;
  animation: ${popIn} 0.25s ease;
`;

/* ── AI card — ticket stub w/ perforated header ── */
const AiCard = styled.div`
  background: white;
  border: 2.5px solid var(--m-black);
  box-shadow: 6px 6px 0 var(--m-black);
  position: relative;

  /* Memphis multi-color top stripe */
  &::before {
    content: '';
    position: absolute;
    top: -5px; left: 0; right: 0;
    height: 5px;
    background: linear-gradient(90deg,
      var(--m-pink) 0%, var(--m-yellow) 33%,
      var(--m-cyan) 66%, var(--m-orange) 100%);
  }

  /* Halftone dot pattern overlay */
  &::after {
    content: '';
    position: absolute;
    inset: 0;
    background-image: radial-gradient(circle, rgba(0,0,0,0.025) 1px, transparent 1px);
    background-size: 14px 14px;
    pointer-events: none;
    z-index: 0;
  }
`;

const AiCardHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 16px 13px;
  background: var(--m-bg-2);
  position: relative;
  border-bottom: 2px solid var(--m-black);

  /* Perforation row at the bottom — paper-tear effect */
  &::after {
    content: '';
    position: absolute;
    bottom: -3px;
    left: 0; right: 0;
    height: 4px;
    background-image: radial-gradient(circle at 5px 0, var(--m-bg-2) 3px, transparent 3.5px);
    background-size: 10px 4px;
    background-repeat: repeat-x;
  }
`;

const StatusDot = styled.span<{ $color: string }>`
  width: 10px; height: 10px;
  background: ${p => p.$color};
  border: 2px solid var(--m-black);
  flex-shrink: 0;
  box-shadow: 1.5px 1.5px 0 var(--m-black);
  transform: rotate(45deg);
`;

const AiCardTitle = styled.span`
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 900;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: var(--m-black);
`;

const QueryStamp = styled.span`
  margin-left: auto;
  background: var(--m-black);
  color: var(--m-yellow);
  padding: 3px 10px;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 900;
  font-size: 10px;
  letter-spacing: 2px;
  text-transform: uppercase;
  border: 2px solid var(--m-black);
  box-shadow: 2px 2px 0 var(--m-pink);
  transform: rotate(2deg);
`;

const AiCardBody = styled.div`
  padding: 16px 18px;
  position: relative;
  z-index: 1;
`;

const ExplanationText = styled.p`
  font-size: 13px;
  color: #444;
  margin-bottom: 12px;
  font-style: italic;
  font-family: 'Space Grotesk', sans-serif;
  line-height: 1.6;
  border-left: 3px solid var(--m-cyan);
  padding: 4px 0 4px 12px;
  background: linear-gradient(90deg, rgba(0,212,255,0.06), transparent 70%);
`;

/* ── SQL block — gutter + syntax highlight ── */
const SqlContainer = styled.div`
  background: #0f0f0f;
  border: 2.5px solid var(--m-black);
  box-shadow: 5px 5px 0 var(--m-pink);
  margin: 12px 0 16px;
  position: relative;
  overflow: hidden;
`;

const SqlBar = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  background: #1a1a1a;
  padding: 6px 12px;
  border-bottom: 1.5px solid #2a2a2a;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 900;
  font-size: 10px;
  letter-spacing: 1.5px;
  color: var(--m-yellow);
  text-transform: uppercase;
  position: relative;

  /* Yellow tape strip top-right */
  &::after {
    content: '';
    position: absolute;
    top: -6px; right: 22px;
    width: 64px; height: 14px;
    background: var(--m-yellow);
    border: 1.5px solid var(--m-black);
    transform: rotate(-5deg);
    opacity: 0.92;
    z-index: 0;
  }

  & > * { position: relative; z-index: 1; }
`;

const SqlBarDots = styled.span`
  display: inline-flex;
  gap: 5px;
  margin-right: 4px;
  span {
    width: 9px; height: 9px;
    border: 1.5px solid var(--m-black);
  }
  span:nth-child(1) { background: var(--m-pink); }
  span:nth-child(2) { background: var(--m-yellow); }
  span:nth-child(3) { background: var(--m-cyan); }
`;

const SqlBody = styled.pre`
  display: flex;
  margin: 0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12.5px;
  line-height: 1.7;
  overflow-x: auto;
`;

const SqlGutter = styled.div`
  flex-shrink: 0;
  padding: 12px 8px 12px 12px;
  background: #131313;
  color: #555;
  font-weight: 600;
  text-align: right;
  user-select: none;
  border-right: 1.5px solid #262626;
  min-width: 36px;

  div { line-height: 1.7; }
`;

const SqlLines = styled.div`
  flex: 1;
  padding: 12px 16px 12px 14px;
  color: #E8E6E0;
  white-space: pre;
  min-width: 0;
  overflow-x: auto;

  .kw  { color: #FF89B5; font-weight: 700; }
  .fn  { color: #FFE66B; font-weight: 600; }
  .num { color: #00D4FF; }
  .str { color: #C6FF00; }
  .cmt { color: #777; font-style: italic; }
`;

/* ── Pipeline chips ── */
const PipelineBar = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0 12px;
`;

const Chip = styled.span<{ $bg?: string; $color?: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  background: ${p => p.$bg || 'var(--m-bg-2)'};
  color: ${p => p.$color || 'var(--m-black)'};
  border: 1.5px solid var(--m-black);
  font-size: 10px;
  font-weight: 800;
  font-family: 'Space Grotesk', sans-serif;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  box-shadow: 1.5px 1.5px 0 var(--m-black);
`;

/* ── Data table section ── */
const TableHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
`;

const RowCount = styled.span`
  font-size: 11px;
  font-weight: 800;
  font-family: 'Space Grotesk', sans-serif;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--m-black);
  background: var(--m-yellow);
  border: 1.5px solid var(--m-black);
  padding: 2px 9px;
  box-shadow: 2px 2px 0 var(--m-black);
`;

/* ── Loading bubble ── */
const LoadingBubble = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: white;
  border: 2px solid var(--m-black);
  box-shadow: var(--shadow-md);
  max-width: 220px;
  animation: ${popIn} 0.2s ease;
`;

const LoadingDots = styled.div`
  display: flex;
  gap: 5px;

  span {
    width: 8px; height: 8px;
    background: var(--m-black);
    border-radius: 50%;
    animation: ${blink} 1.2s infinite;

    &:nth-child(2) { animation-delay: 0.22s; background: var(--m-pink); }
    &:nth-child(3) { animation-delay: 0.44s; background: var(--m-cyan); }
  }
`;

const LoadingText = styled.span`
  font-family: 'Space Grotesk', sans-serif;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--m-black);
`;

/* ════════════════════════════════════════════
   WELCOME SCREEN
   ════════════════════════════════════════════ */
const WelcomeArea = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  position: relative;
  z-index: 1;
  overflow: hidden;

  /* Bold Memphis colored stripes at top & bottom edges */
  &::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 8px;
    background: linear-gradient(
      90deg,
      var(--m-pink)   0%,
      var(--m-yellow) 20%,
      var(--m-cyan)   40%,
      var(--m-orange) 60%,
      var(--m-purple) 80%,
      var(--m-green)  100%
    );
    pointer-events: none;
    z-index: 1;
  }
  &::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(
      90deg,
      var(--m-green)  0%,
      var(--m-purple) 25%,
      var(--m-orange) 50%,
      var(--m-cyan)   75%,
      var(--m-pink)   100%
    );
    pointer-events: none;
    z-index: 1;
  }
`;

/* ── Hero stage: asymmetric grid (text left, collage right) ── */
const WelcomeStage = styled.div`
  position: relative;
  width: 100%;
  max-width: 1040px;
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 36px;
  align-items: center;
  z-index: 2;

  @media (max-width: 880px) {
    grid-template-columns: 1fr;
    gap: 16px;
  }
`;

const WelcomeLeft = styled.div`
  position: relative;
`;

/* Yellow sticker tag — version label */
const HeroTag = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--m-yellow);
  border: 2px solid var(--m-black);
  box-shadow: 3px 3px 0 var(--m-black);
  padding: 4px 10px 4px 8px;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 900;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--m-black);
  margin-bottom: 22px;
  transform: rotate(-2deg);

  &::before {
    content: '';
    width: 8px; height: 8px;
    background: var(--m-pink);
    border: 1.5px solid var(--m-black);
    display: inline-block;
  }
`;

/* Massive multi-color hero typography */
const HeroTitle = styled.h1`
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 900;
  font-size: clamp(44px, 6vw, 78px);
  line-height: 0.92;
  letter-spacing: -2.5px;
  text-transform: uppercase;
  color: var(--m-black);
  margin: 0 0 18px;

  span { display: inline-block; vertical-align: baseline; }

  .w-ask {
    background: var(--m-yellow);
    padding: 0 14px 4px;
    border: 3px solid var(--m-black);
    box-shadow: 5px 5px 0 var(--m-black);
    transform: rotate(-1.8deg);
    margin-right: 10px;
  }
  .w-your { color: var(--m-pink); font-style: italic; }
  .w-data { color: var(--m-black); }
  .w-dash { color: var(--m-orange); font-weight: 900; padding: 0 4px; }
  .w-get  {
    background: var(--m-cyan);
    padding: 0 14px 4px;
    border: 3px solid var(--m-black);
    box-shadow: 5px 5px 0 var(--m-pink);
    transform: rotate(2deg);
    margin-right: 10px;
  }
  .w-sql {
    color: var(--m-purple);
    font-style: italic;
    text-decoration: underline wavy var(--m-orange);
    text-underline-offset: 10px;
  }

  @media (max-width: 880px) {
    font-size: clamp(34px, 9vw, 52px);
  }
`;

const HeroSub = styled.p`
  font-family: 'Space Grotesk', sans-serif;
  font-size: 14px;
  font-weight: 600;
  color: #555;
  margin: 18px 0 24px;
  max-width: 480px;
  line-height: 1.55;
  border-left: 4px solid var(--m-cyan);
  padding-left: 12px;

  strong {
    color: var(--m-black);
    font-weight: 800;
    background: rgba(255,230,0,0.45);
    padding: 0 4px;
  }
`;

/* Sticker grid for sample queries */
const StickerGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px 16px;
  max-width: 560px;
`;

const Sticker = styled.button<{ $tone: string; $tilt: number }>`
  position: relative;
  text-align: left;
  padding: 14px 14px 14px 46px;
  background: ${p => p.$tone};
  border: 2.5px solid var(--m-black);
  box-shadow: 4px 4px 0 var(--m-black);
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 700;
  font-size: 12.5px;
  line-height: 1.4;
  color: var(--m-black);
  cursor: var(--cur-pointer);
  transform: rotate(${p => p.$tilt}deg);
  transition: transform 0.14s, box-shadow 0.14s;

  &:hover {
    transform: rotate(0deg) translate(-2px, -2px);
    box-shadow: 7px 7px 0 var(--m-black);
  }
  &:active {
    transform: rotate(0deg) translate(2px, 2px);
    box-shadow: none;
  }
`;

const StickerNum = styled.span`
  position: absolute;
  top: -10px; left: -10px;
  width: 30px; height: 30px;
  background: var(--m-black);
  color: var(--m-yellow);
  border: 2.5px solid var(--m-black);
  display: flex; align-items: center; justify-content: center;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 900;
  font-size: 13px;
  letter-spacing: 0;
  box-shadow: 2.5px 2.5px 0 var(--m-pink);
`;

/* Right-side collage of Memphis shapes */
const Collage = styled.div`
  position: relative;
  height: 420px;
  width: 100%;
  @media (max-width: 880px) { display: none; }
`;

const CollageA = styled.div`
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%) rotate(-4deg);
  width: 150px; height: 150px;
  background: var(--m-yellow);
  border: 4px solid var(--m-black);
  box-shadow: 9px 9px 0 var(--m-black);
  display: flex; align-items: center; justify-content: center;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 900;
  font-size: 96px;
  color: var(--m-black);
  animation: ${floatShape} 4s ease-in-out infinite;
  z-index: 3;
`;

const CollagePill = styled.div`
  position: absolute;
  top: 6%; right: 5%;
  width: 150px; height: 60px;
  background: var(--m-pink);
  border: 3px solid var(--m-black);
  box-shadow: 5px 5px 0 var(--m-black);
  border-radius: 30px;
  transform: rotate(-10deg);
  animation: ${floatShape} 6s ease-in-out infinite;
`;

const CollageStripeBall = styled.div`
  position: absolute;
  top: 0%; right: 38%;
  width: 76px; height: 76px;
  background: repeating-linear-gradient(
    90deg,
    var(--m-orange) 0 8px,
    var(--m-yellow) 8px 16px
  );
  border: 3px solid var(--m-black);
  border-radius: 50%;
  transform: rotate(20deg);
  box-shadow: 4px 4px 0 var(--m-black);
  animation: ${floatShape} 7s ease-in-out infinite;
  animation-delay: 0.4s;
`;

const CollageHalf = styled.div`
  position: absolute;
  top: 14%; left: 22%;
  width: 90px; height: 45px;
  background: var(--m-cyan);
  border: 3px solid var(--m-black);
  border-radius: 90px 90px 0 0;
  transform: rotate(-18deg);
  box-shadow: 4px 4px 0 var(--m-black);
  animation: ${floatShape} 7s ease-in-out infinite;
  animation-delay: 1.2s;
`;

const CollageDots = styled.div`
  position: absolute;
  bottom: 22%; right: 4%;
  width: 96px; height: 96px;
  background-color: var(--m-bg);
  background-image: radial-gradient(circle, var(--m-purple) 28%, transparent 30%);
  background-size: 16px 16px;
  border: 3px solid var(--m-black);
  box-shadow: 5px 5px 0 var(--m-black);
  animation: ${floatShape} 8s ease-in-out infinite;
`;

const CollageZigzag = styled.div`
  position: absolute;
  bottom: 14%; left: 14%;
  width: 130px; height: 22px;
  background: repeating-linear-gradient(
    -45deg,
    var(--m-purple) 0 9px,
    var(--m-bg) 9px 18px
  );
  border: 2.5px solid var(--m-black);
  transform: rotate(-6deg);
`;

const CollagePlus = styled.div`
  position: absolute;
  top: 28%; right: 28%;
  width: 36px; height: 36px;
  background:
    linear-gradient(var(--m-black) 0 0) center/100% 7px no-repeat,
    linear-gradient(var(--m-black) 0 0) center/7px 100% no-repeat;
  animation: ${floatShape} 4.5s ease-in-out infinite;
  animation-delay: 0.4s;
`;

const CollageTriangle = styled.div`
  position: absolute;
  bottom: 4%; right: 30%;
  width: 0; height: 0;
  border-left: 26px solid transparent;
  border-right: 26px solid transparent;
  border-bottom: 46px solid var(--m-green);
  filter: drop-shadow(3px 3px 0 var(--m-black));
  transform: rotate(15deg);
  animation: ${floatShape} 5.5s ease-in-out infinite;
  animation-delay: 0.8s;
`;

const CollageSquare = styled.div`
  position: absolute;
  top: 60%; left: 6%;
  width: 56px; height: 56px;
  background: var(--m-orange);
  border: 3px solid var(--m-black);
  box-shadow: 5px 5px 0 var(--m-yellow);
  transform: rotate(15deg);
  animation: ${floatShape} 6s ease-in-out infinite;
  animation-delay: 0.9s;
`;

/* ════════════════════════════════════════════
   INPUT BAR
   ════════════════════════════════════════════ */
const InputBar = styled.div`
  border-top: 3px solid var(--m-black);
  padding: 10px 24px 14px;
  background: white;
  position: relative;
  z-index: 10;

  /* Memphis multi-stop accent bar */
  &::before {
    content: '';
    position: absolute;
    top: -7px; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg,
      var(--m-yellow) 0%, var(--m-pink) 25%,
      var(--m-cyan) 50%, var(--m-orange) 75%,
      var(--m-purple) 100%
    );
  }

  /* Halftone dot pattern overlay */
  &::after {
    content: '';
    position: absolute;
    inset: 0;
    background-image: radial-gradient(circle, rgba(0,0,0,0.025) 1px, transparent 1px);
    background-size: 12px 12px;
    pointer-events: none;
  }
`;

const QuickChipRow = styled.div`
  max-width: 820px;
  margin: 0 auto 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  position: relative;
  z-index: 1;
`;

const QuickChip = styled.button<{ $active?: boolean; $accent?: string }>`
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  background: ${p => p.$active ? (p.$accent || 'var(--m-yellow)') : 'white'};
  color: ${p => p.$active ? (p.$accent === 'var(--m-pink)' ? 'white' : 'var(--m-black)') : 'var(--m-black)'};
  border: 1.5px solid var(--m-black);
  box-shadow: 2px 2px 0 var(--m-black);
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 800;
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.7px;
  cursor: pointer;
  transition: transform 0.08s, box-shadow 0.08s, background 0.12s;
  white-space: nowrap;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;

  &:hover:not(:disabled) {
    transform: translate(-1px, -1px);
    box-shadow: 3px 3px 0 var(--m-black);
    background: ${p => p.$active ? (p.$accent || 'var(--m-yellow)') : 'var(--m-yellow)'};
  }
  &:active {
    transform: translate(2px, 2px);
    box-shadow: none;
  }
  &:disabled { opacity: 0.55; cursor: not-allowed; }
`;

const ChipDivider = styled.span`
  width: 2px;
  height: 18px;
  background: var(--m-black);
  margin: 0 4px;
  display: inline-block;
`;

const InputRow = styled.div`
  max-width: 820px;
  margin: 0 auto;
  display: flex;
  gap: 12px;
  align-items: center;
  position: relative;
  z-index: 1;
`;

const StyledInput = styled(Input)`
  && {
    border: 2.5px solid var(--m-black) !important;
    border-radius: 0 !important;
    background: var(--m-bg) !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    color: var(--m-black) !important;
    height: 50px !important;
    padding: 0 18px !important;
    box-shadow: 4px 4px 0 var(--m-black) !important;
    transition: box-shadow 0.1s, border-color 0.1s !important;

    &::placeholder {
      color: #999 !important;
      font-weight: 500 !important;
      font-size: 13px !important;
    }

    &:focus {
      border-color: var(--m-pink) !important;
      box-shadow: 4px 4px 0 var(--m-pink) !important;
      background: white !important;
    }

    &:disabled {
      opacity: 0.6 !important;
    }
  }
`;

const SendBtn = styled.button<{ $loading?: boolean }>`
  width: 50px; height: 50px;
  background: var(--m-pink);
  border: 2.5px solid var(--m-black);
  box-shadow: 4px 4px 0 var(--m-black);
  color: white;
  cursor: ${p => p.$loading ? 'wait' : 'var(--cur-pointer)'};
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
  transition: all 0.18s cubic-bezier(0.34, 1.56, 0.64, 1);
  position: relative;
  overflow: visible;

  /* Halftone dots on the surface */
  &::before {
    content: '';
    position: absolute;
    inset: 3px;
    background-image: radial-gradient(circle, rgba(255,255,255,0.18) 1.2px, transparent 1.2px);
    background-size: 6px 6px;
    pointer-events: none;
  }

  /* Yellow corner sticker — shape morphs on hover */
  &::after {
    content: '';
    position: absolute;
    top: -6px; left: -6px;
    width: 14px; height: 14px;
    background: var(--m-yellow);
    border: 2px solid var(--m-black);
    transition: transform 0.22s, background 0.22s, border-radius 0.22s;
  }

  &:hover:not(:disabled) {
    transform: translate(-2px, -2px) rotate(-4deg);
    box-shadow: 6px 6px 0 var(--m-black);
    background: #e0002c;

    &::after {
      transform: rotate(45deg) scale(1.2);
      background: var(--m-cyan);
      border-radius: 4px;
    }
  }
  &:active {
    transform: translate(3px, 3px) rotate(0);
    box-shadow: none;
  }
  &:disabled { opacity: 0.5; cursor: not-allowed; }

  & > * { position: relative; z-index: 1; }
`;

/* ══════════════════════════════════════════════
   MAIN COMPONENT
   ══════════════════════════════════════════════ */
export default function HomePage() {
  const { threads, setThreads, activeId, setActiveId } = useChat();
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const debugMode = true;
  const [pipelineSteps, setPipelineSteps] = useState<ProgressEvent[]>([]);
  // Streaming token state — real-time LLM output (Stage 11 CoT + Stage 12 SQL)
  const [cotStreamingText, setCotStreamingText] = useState('');
  const [sqlStreamingText, setSqlStreamingText] = useState('');
  const [showCotWindow, setShowCotWindow] = useState(false);
  const [showSqlWindow, setShowSqlWindow] = useState(false);
  const [activeStreamingStage, setActiveStreamingStage] = useState<'reasoning' | 'sql' | null>(null);

  const cotStreamingRef = useRef(''); // avoid stale closure in token callback
  const sqlStreamingRef = useRef(''); // avoid stale closure in token callback
  const cotScrollRef = useRef<HTMLDivElement>(null); // inner scroll container for auto-scroll
  const sqlScrollRef = useRef<HTMLDivElement>(null); // inner scroll container for auto-scroll
  const progressScrollRef = useRef<HTMLDivElement>(null); // scroll container for pipeline progress
  // Thought drawer state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTrace, setDrawerTrace] = useState<DebugTrace | null>(null);
  const [drawerSeconds, setDrawerSeconds] = useState(0);
  const startTimeRef = useRef<number>(0);
  // Accumulator ref — avoids stale closure when reading steps after await
  const stepsAccRef = useRef<ProgressEvent[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  // mounted guard for createPortal (Next.js SSR safe)
  const [mounted, setMounted] = useState(false);

  const active = threads.find(t => t.id === activeId);

  // Auto-scroll inner streaming boxes to bottom on every new token
  useEffect(() => {
    if (cotScrollRef.current && activeStreamingStage === 'reasoning') {
      cotScrollRef.current.scrollTop = cotScrollRef.current.scrollHeight;
    }
  }, [cotStreamingText, activeStreamingStage]);

  useEffect(() => {
    if (sqlScrollRef.current && activeStreamingStage === 'sql') {
      sqlScrollRef.current.scrollTop = sqlScrollRef.current.scrollHeight;
    }
  }, [sqlStreamingText, activeStreamingStage]);

  useEffect(() => { setMounted(true); }, []);

  // Scroll to bottom on new message (final result)
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [active?.messages.length]);

  // Scroll to bottom on every new pipeline stage — keeps live timeline in view
  useEffect(() => {
    if (pipelineSteps.length > 0) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
      if (progressScrollRef.current) {
        // Scroll the inner pipeline box down
        progressScrollRef.current.scrollTo({
          top: progressScrollRef.current.scrollHeight,
          behavior: 'smooth'
        });
      }
    }
  }, [pipelineSteps.length]);

  // Scroll to bottom when streaming box appears/switches stage
  useEffect(() => {
    if (activeStreamingStage) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [activeStreamingStage]);

  const newThread = () => {
    const id = Date.now().toString();
    const t: Thread = { id, title: 'New conversation', messages: [] };
    setThreads(prev => [t, ...prev]);
    setActiveId(id);
  };

  const sendMessage = async (overrideText?: string) => {
    const question = (overrideText || input).trim();
    if (!question || loading) return;
    if (!overrideText) setInput('');

    let tid = activeId;
    if (!tid) {
      const id = Date.now().toString();
      const t: Thread = { id, title: question.slice(0, 40), messages: [] };
      setThreads(prev => [t, ...prev]);
      setActiveId(id);
      tid = id;
    }

    setThreads(prev => prev.map(t =>
      t.id === tid
        ? {
          ...t,
          title: t.messages.length === 0 ? question.slice(0, 40) : t.title,
          messages: [...t.messages, { role: 'user', text: question }],
        }
        : t
    ));

    setLoading(true);
    setPipelineSteps([]);
    stepsAccRef.current = [];      // reset accumulator
    // Reset streaming state
    setCotStreamingText('');
    setSqlStreamingText('');
    setShowCotWindow(false);
    setShowSqlWindow(false);
    setActiveStreamingStage(null);
    cotStreamingRef.current = '';
    sqlStreamingRef.current = '';
    startTimeRef.current = Date.now();
    try {
      const thread = threads.find(t => t.id === tid);
      const existing_session_id = thread?.session_id || '';

      const res = await api.askStream(
        question,
        existing_session_id || '',
        debugMode,
        {},
        (evt) => {
          // Merge: if same stage already exists, update its detail; otherwise append
          const existing = stepsAccRef.current.findIndex(s => s.stage === evt.stage);
          if (existing >= 0 && evt.detail) {
            // Second event for this stage — update detail only
            stepsAccRef.current = stepsAccRef.current.map((s, i) =>
              i === existing ? { ...s, detail: evt.detail } : s
            );
          } else if (existing < 0) {
            // First event for this stage — append new step
            stepsAccRef.current = [...stepsAccRef.current, evt];
          }
          setPipelineSteps([...stepsAccRef.current]);
        },
        // onToken — fired for each LLM token from Stage 11 (CoT) and Stage 12 (SQL)
        (evt: TokenEvent) => {
          if (evt.stage === 'reasoning') {
            setShowCotWindow(true);
            cotStreamingRef.current += evt.text;
            setCotStreamingText(cotStreamingRef.current);
            setActiveStreamingStage('reasoning');
          } else if (evt.stage === 'sql') {
            setShowSqlWindow(true);
            sqlStreamingRef.current += evt.text;
            setSqlStreamingText(sqlStreamingRef.current);
            setActiveStreamingStage('sql');
          }
        },
      );

      const returned_session_id = res.pipeline_info?.session_id || existing_session_id;
      if (returned_session_id) {
        setThreads(prev => prev.map(t =>
          t.id === tid ? { ...t, session_id: returned_session_id } : t
        ));
      }

      const aiMsg: Msg = {
        role: 'ai',
        text: res.valid ? 'Generated SQL' : (res.error || 'Could not generate SQL'),
        sql: res.sql,
        columns: res.columns,
        rows: res.rows,
        rowCount: res.row_count,
        explanation: res.explanation,
        valid: res.valid,
        pipelineInfo: res.pipeline_info ? {
          reasoning_steps: res.pipeline_info.reasoning_steps,
          columns_pruned: res.pipeline_info.columns_pruned,
          candidates_generated: res.pipeline_info.candidates_generated,
          voting_method: res.pipeline_info.voting_method,
          glossary_matches: res.pipeline_info.glossary_matches,
          guardian_passed: res.pipeline_info.guardian_passed,
          sub_intent: res.pipeline_info.sub_intent,
          session_id: res.pipeline_info.session_id,
          enriched_question: res.pipeline_info.enriched_question,
          was_enriched: res.pipeline_info.was_enriched,
        } : undefined,
        debugTrace: res.debug_trace,
        originalQuestion: question,
        // Use stepsAccRef (NOT stale pipelineSteps state) to capture all steps
        thoughtSteps: stepsAccRef.current.length > 0 ? [...stepsAccRef.current] : undefined,
        thoughtSeconds: stepsAccRef.current.length > 0
          ? Math.round((Date.now() - startTimeRef.current) / 1000)
          : undefined,
      };

      setThreads(prev => prev.map(t =>
        t.id === tid ? { ...t, messages: [...t.messages, aiMsg] } : t
      ));
      // Streaming box done — hide it once final result is rendered
      setShowCotWindow(false);
      setShowSqlWindow(false);
      setCotStreamingText('');
      setSqlStreamingText('');
      setActiveStreamingStage(null);
      cotStreamingRef.current = '';
      sqlStreamingRef.current = '';
    } catch (err: any) {
      message.error(err.message || 'Failed to connect to API server');
      setShowCotWindow(false);
      setShowSqlWindow(false);
      setCotStreamingText('');
      setSqlStreamingText('');
      setActiveStreamingStage(null);
      cotStreamingRef.current = '';
      sqlStreamingRef.current = '';
      setThreads(prev => prev.map(t =>
        t.id === tid
          ? { ...t, messages: [...t.messages, { role: 'ai', text: err.message || 'Server connection error' }] }
          : t
      ));
    }
    setLoading(false);
  };

  const generateChart = async (msgIndex: number) => {
    if (!active) return;
    const msg = active.messages[msgIndex];
    if (!msg?.sql || !msg.originalQuestion) return;

    setThreads(prev => prev.map(t =>
      t.id === active.id
        ? {
          ...t, messages: t.messages.map((m, i) =>
            i === msgIndex ? { ...m, chartLoading: true, chartError: undefined } : m
          )
        }
        : t
    ));

    try {
      const res = await api.generateChart(msg.originalQuestion, msg.sql);
      setThreads(prev => prev.map(t =>
        t.id === active.id ? {
          ...t, messages: t.messages.map((m, i) =>
            i === msgIndex ? {
              ...m, chartLoading: false,
              chartSpec: res.chart_schema,
              chartData: res.data?.rows || m.rows,
              chartReasoning: res.reasoning,
              chartType: res.chart_type,
              chartError: res.error || undefined,
            } : m
          )
        } : t
      ));
    } catch (err: any) {
      setThreads(prev => prev.map(t =>
        t.id === active.id ? {
          ...t, messages: t.messages.map((m, i) =>
            i === msgIndex
              ? { ...m, chartLoading: false, chartError: err.message || 'Chart generation failed' }
              : m
          )
        } : t
      ));
    }
  };

  /* ── Sidebar JSX ── */
  const sidebar = (
    <SidebarSection>
      <SidebarLabel>Threads</SidebarLabel>
      <NewThreadBtn onClick={newThread}>New Conversation</NewThreadBtn>
      {threads.map(t => (
        <ThreadItem key={t.id} $active={t.id === activeId} onClick={() => setActiveId(t.id)}>
          {t.title}
        </ThreadItem>
      ))}
    </SidebarSection>
  );

  /* ── Pipeline info chips ── */
  const renderPipelineInfo = (info: Msg['pipelineInfo']) => {
    if (!info) return null;
    return (
      <PipelineBar>
        {info.sub_intent && (
          <Chip $bg="var(--m-cyan)" $color="var(--m-black)">{info.sub_intent}</Chip>
        )}
        {info.candidates_generated != null && info.candidates_generated > 0 && (
          <Chip $bg="var(--m-bg-2)">{info.candidates_generated} candidates · {info.voting_method}</Chip>
        )}
        {info.columns_pruned != null && info.columns_pruned > 0 && (
          <Chip $bg="var(--m-bg-3)">
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" style={{ display: 'inline', verticalAlign: 'middle', marginRight: 3 }}><circle cx="3" cy="4" r="2" fill="none" stroke="currentColor" strokeWidth="1.2" /><circle cx="3" cy="8" r="2" fill="none" stroke="currentColor" strokeWidth="1.2" /><line x1="5" y1="5" x2="11" y2="2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="square" /><line x1="5" y1="7" x2="11" y2="10" stroke="currentColor" strokeWidth="1.2" strokeLinecap="square" /></svg>
            {info.columns_pruned} cols
          </Chip>
        )}
        {info.glossary_matches != null && info.glossary_matches > 0 && (
          <Chip $bg="var(--m-green)" $color="var(--m-black)">
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" style={{ display: 'inline', verticalAlign: 'middle', marginRight: 3 }}><rect x="2" y="1" width="8" height="10" fill="none" stroke="currentColor" strokeWidth="1.2" /><rect x="2" y="1" width="2" height="10" fill="currentColor" /><line x1="5" y1="4" x2="9" y2="4" stroke="currentColor" strokeWidth="1" /><line x1="5" y1="6" x2="9" y2="6" stroke="currentColor" strokeWidth="1" /></svg>
            {info.glossary_matches} glossary
          </Chip>
        )}
        {info.guardian_passed === false && (
          <Chip $bg="var(--m-red)" $color="white">
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" style={{ display: 'inline', verticalAlign: 'middle', marginRight: 3 }}><path d="M6 1 L11 3 L11 7 C11 9.5 6 11 6 11 C6 11 1 9.5 1 7 L1 3 Z" fill="none" stroke="white" strokeWidth="1.2" /><line x1="4" y1="4" x2="8" y2="8" stroke="white" strokeWidth="1.2" /><line x1="8" y1="4" x2="4" y2="8" stroke="white" strokeWidth="1.2" /></svg>
            Blocked
          </Chip>
        )}
        {info.reasoning_steps && info.reasoning_steps.length > 0 && (
          <Chip $bg="var(--m-purple)" $color="white">
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" style={{ display: 'inline', verticalAlign: 'middle', marginRight: 3 }}><rect x="1" y="8" width="3" height="3" fill="white" stroke="white" strokeWidth="0.5" /><rect x="4.5" y="5" width="3" height="6" fill="white" stroke="white" strokeWidth="0.5" /><rect x="8" y="2" width="3" height="9" fill="white" stroke="white" strokeWidth="0.5" /></svg>
            {info.reasoning_steps.length} steps
          </Chip>
        )}
        {info.was_enriched && info.enriched_question && (
          <Tooltip title={`Câu hỏi được diễn giải: "${info.enriched_question}"`}>
            <Chip $bg="var(--m-orange)" $color="white">
              <svg width="10" height="10" viewBox="0 0 12 12" fill="none" style={{ display: 'inline', verticalAlign: 'middle', marginRight: 3 }}><rect x="1" y="1" width="10" height="7" fill="none" stroke="white" strokeWidth="1.2" /><polygon points="3,8 3,11 6,8" fill="white" /></svg>
              Context
            </Chip>
          </Tooltip>
        )}
      </PipelineBar>
    );
  };


  /* ── Data table ── */
  const renderTable = (columns: string[], rows: any[]) => {
    const cols = columns.map(c => ({
      title: c,
      dataIndex: c,
      key: c,
      ellipsis: true,
      render: (v: any) => <span style={{ fontSize: 13, fontFamily: 'Space Grotesk', fontWeight: 500 }}>{v != null ? String(v) : '-'}</span>,
    }));
    return (
      <Table
        dataSource={rows.map((r, i) => ({ ...r, key: i }))}
        columns={cols}
        size="small"
        pagination={{ pageSize: 10, size: 'small', hideOnSinglePage: true }}
        scroll={{ x: 'max-content' }}
        style={{ marginTop: 8 }}
      />
    );
  };

  /* ── Sample queries ── */
  const samples = [
    'Top 5 sản phẩm bán chạy nhất',
    'Doanh thu từng tháng năm 2013',
    'Khách hàng mua nhiều nhất',
    'So sánh doanh thu theo quý',
  ];

  return (
    <>
      <RequireConnection>
        <Head><title>Home — askDataAI</title></Head>
        <SiderLayout sidebar={sidebar}>
          <ChatWrapper>
            {!active || active.messages.length === 0 ? (
              /* ═══ Welcome Screen ═══ */
              <WelcomeArea>
                <WelcomeStage>
                  <WelcomeLeft>
                    <HeroTag>askDataAI</HeroTag>
                    <HeroTitle>
                      <span className="w-ask">Ask</span>
                      <span className="w-your">your</span>
                      <br />
                      <span className="w-data">data</span>
                      <span className="w-dash">—</span>
                      <br />
                      <span className="w-get">get</span>
                      <span className="w-sql">SQL.</span>
                    </HeroTitle>
                    <HeroSub>
                      Vietnamese-first <strong>Text-to-SQL</strong>. Ask in plain language,
                      let the 16-stage pipeline reason → retrieve schema → generate → vote → guard.
                    </HeroSub>
                    <StickerGrid>
                      {samples.map((s, i) => {
                        const tones = ['var(--m-yellow)', 'var(--m-cyan)', 'var(--m-pink)', 'var(--m-green)'];
                        const tilts = [-1.8, 1.6, -1.4, 2];
                        return (
                          <Sticker
                            key={s}
                            $tone={tones[i % tones.length]}
                            $tilt={tilts[i % tilts.length]}
                            onClick={() => sendMessage(s)}
                          >
                            <StickerNum>{String(i + 1).padStart(2, '0')}</StickerNum>
                            {s}
                          </Sticker>
                        );
                      })}
                    </StickerGrid>
                  </WelcomeLeft>

                  <Collage>
                    <CollagePill />
                    <CollageStripeBall />
                    <CollageHalf />
                    <CollagePlus />
                    <CollageDots />
                    <CollageSquare />
                    <CollageZigzag />
                    <CollageTriangle />
                    <CollageA>A</CollageA>
                  </Collage>
                </WelcomeStage>
              </WelcomeArea>
            ) : (
              /* ═══ Messages ═══ */
              <MessagesArea>
                <MessagesInner>
                  {active.messages.map((msg, i) => {
                    const userIdx = active.messages.slice(0, i + 1).filter(m => m.role === 'user').length;
                    const aiIdx = active.messages.slice(0, i + 1).filter(m => m.role === 'ai').length;
                    return msg.role === 'user' ? (
                      <UserBubble key={i}>
                        <UserBadge>Q · {String(userIdx).padStart(2, '0')}</UserBadge>
                        {msg.text}
                      </UserBubble>
                    ) : (
                      <AiBubble key={i}>
                        <AiCard>
                          <AiCardHeader>
                            <StatusDot $color={msg.valid ? 'var(--m-green)' : 'var(--m-red)'} />
                            <AiCardTitle>{msg.valid ? 'Query Result' : 'Error'}</AiCardTitle>
                            <QueryStamp>#{String(aiIdx).padStart(2, '0')}</QueryStamp>
                          </AiCardHeader>
                          <AiCardBody>
                            {/* Thought chip — opens drawer with full pipeline trace */}
                            {(msg.debugTrace?.stages?.length || msg.thoughtSteps?.length) ? (
                              <ThoughtBtn
                                onClick={() => {
                                  setDrawerTrace(msg.debugTrace ?? null);
                                  setDrawerSeconds(msg.thoughtSeconds ?? 0);
                                  setDrawerOpen(true);
                                }}
                              >
                                ⚡ Thought for {msg.thoughtSeconds ?? 0}s
                              </ThoughtBtn>
                            ) : null}
                            {msg.explanation && (
                              <ExplanationText>{msg.explanation}</ExplanationText>
                            )}
                            {msg.pipelineInfo && renderPipelineInfo(msg.pipelineInfo)}
                            {msg.sql && (() => {
                              const lines = msg.sql.split('\n');
                              return (
                                <SqlContainer>
                                  <SqlBar>
                                    <SqlBarDots><span /><span /><span /></SqlBarDots>
                                    SQL · {lines.length} {lines.length === 1 ? 'line' : 'lines'}
                                  </SqlBar>
                                  <SqlBody>
                                    <SqlGutter>
                                      {lines.map((_, idx) => <div key={idx}>{idx + 1}</div>)}
                                    </SqlGutter>
                                    <SqlLines>{highlightSql(msg.sql)}</SqlLines>
                                  </SqlBody>
                                </SqlContainer>
                              );
                            })()}

                            {msg.columns && msg.rows && msg.rows.length > 0 && (
                              <>
                                <TableHeader>
                                  <RowCount>{msg.rowCount} rows</RowCount>
                                  {msg.sql && !msg.chartSpec && !msg.chartLoading && (
                                    <Button
                                      size="small"
                                      icon={<IconChart />}
                                      onClick={() => generateChart(i)}
                                      style={{
                                        fontFamily: 'Space Grotesk',
                                        fontWeight: 700,
                                        fontSize: 11,
                                        textTransform: 'uppercase',
                                        letterSpacing: '0.5px',
                                      }}
                                    >
                                      Tạo biểu đồ
                                    </Button>
                                  )}
                                  {msg.chartLoading && (
                                    <span style={{
                                      color: 'var(--m-pink)',
                                      fontSize: 11,
                                      fontWeight: 700,
                                      fontFamily: 'Space Grotesk',
                                      textTransform: 'uppercase',
                                      letterSpacing: '0.5px',
                                    }}>
                                      <IconLoading />
                                      Generating chart...
                                    </span>
                                  )}
                                </TableHeader>
                                {renderTable(msg.columns, msg.rows)}
                              </>
                            )}

                            {/* No rows message */}
                            {msg.valid && msg.rows && msg.rows.length === 0 && (
                              <div style={{
                                padding: '16px',
                                background: 'var(--m-bg-2)',
                                border: '2px dashed var(--m-black)',
                                textAlign: 'center',
                                fontFamily: 'Space Grotesk',
                                fontSize: 12,
                                fontWeight: 700,
                                textTransform: 'uppercase',
                                letterSpacing: '0.5px',
                                color: '#777',
                              }}>
                                📭 No data returned for this query
                              </div>
                            )}

                            {/* Error */}
                            {!msg.valid && (
                              <div style={{
                                padding: '12px 14px',
                                background: 'rgba(255,23,68,0.08)',
                                border: '2px solid var(--m-red)',
                                boxShadow: '3px 3px 0 var(--m-red)',
                                fontFamily: 'Space Grotesk',
                                fontSize: 13,
                                fontWeight: 600,
                                color: 'var(--m-red)',
                              }}>
                                ⚠ {msg.text}
                              </div>
                            )}

                            {/* Chart */}
                            {msg.chartSpec && Object.keys(msg.chartSpec).length > 0 && (
                              <VegaChart
                                spec={msg.chartSpec}
                                data={msg.chartData}
                                reasoning={msg.chartReasoning}
                                chartType={msg.chartType}
                              />
                            )}
                            {msg.chartError && !msg.chartLoading && (
                              <div style={{
                                color: 'var(--m-red)', fontSize: 12, marginTop: 8,
                                padding: '6px 12px',
                                background: 'rgba(255,23,68,0.08)',
                                border: '2px solid var(--m-red)',
                                fontFamily: 'Space Grotesk', fontWeight: 600,
                              }}>
                                ⚠ Chart error: {msg.chartError}
                              </div>
                            )}

                          </AiCardBody>
                        </AiCard>
                      </AiBubble>
                    );
                  })}

                  {/* Pipeline Progress Panel — live timeline, hides when done */}
                  {loading && (
                    <AiBubble>
                      <ProgressPanel>
                        <ProgressHeader>
                          <IconLoading />
                          <ProgressTitle>Pipeline đang chạy</ProgressTitle>
                          <span style={{
                            marginLeft: 'auto',
                            fontSize: 10,
                            fontWeight: 700,
                            fontFamily: 'Space Grotesk',
                            color: 'var(--m-pink)',
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                          }}>
                            {pipelineSteps.length > 0
                              ? `${pipelineSteps.length} / ~14 stages`
                              : 'Khởi động...'}
                          </span>
                        </ProgressHeader>

                        {/* Progress bar */}
                        <PipelineTrack>
                          <PipelineFill
                            $pct={
                              pipelineSteps.length > 0
                                ? (STAGE_PCT[pipelineSteps[pipelineSteps.length - 1].stage] ?? 50)
                                : 2
                            }
                          />
                        </PipelineTrack>

                        {/* Live step timeline */}
                        <LiveStepList ref={progressScrollRef}>
                          {pipelineSteps.map((s, i) => {
                            const isLast = i === pipelineSteps.length - 1;
                            const hasDone = !!s.detail;
                            return (
                              <LiveStepRow key={s.stage} $active={isLast && !hasDone} $done={hasDone}>
                                <LiveDot $active={isLast && !hasDone} $done={hasDone}>
                                  {getStageIcon(s.stage)}
                                </LiveDot>
                                <LiveContent>
                                  <LiveLabel $active={isLast && !hasDone}>{stripEmoji(s.label)}</LiveLabel>
                                  {s.detail && <LiveDetail>{stripEmoji(s.detail)}</LiveDetail>}
                                </LiveContent>
                              </LiveStepRow>
                            );
                          })}
                        </LiveStepList>
                      </ProgressPanel>
                    </AiBubble>
                  )}

                  {/* ═══ ChatGPT-style streaming box ═══
                     Rendered OUTSIDE ProgressPanel so it never causes
                     the pipeline card to resize/shift. Fixed height.
                */}
                  {/* ── CoT Streaming Box ── */}
                  {showCotWindow && (
                    <AiBubble style={{ marginTop: 14, marginBottom: showSqlWindow ? 16 : 0 }}>
                      <StreamBox $variant="cot">
                        <StreamHead $variant="cot">
                          <IconThought />
                          <StreamTitle>Chain-of-Thought</StreamTitle>
                          {activeStreamingStage === 'reasoning' && <LiveBadge>LIVE</LiveBadge>}
                        </StreamHead>
                        <StreamBody $variant="cot" ref={cotScrollRef}>
                          {cotStreamingText || ' '}
                          {activeStreamingStage === 'reasoning' && <StreamCursor $color="var(--m-pink)" />}
                        </StreamBody>
                      </StreamBox>
                    </AiBubble>
                  )}

                  {showSqlWindow && (
                    <AiBubble style={{ marginTop: 14 }}>
                      <StreamBox $variant="sql">
                        <StreamHead $variant="sql">
                          <IconBolt />
                          <StreamTitle $dark>SQL Generation</StreamTitle>
                          {activeStreamingStage === 'sql' && <LiveBadge>LIVE</LiveBadge>}
                        </StreamHead>
                        <StreamBody $variant="sql" ref={sqlScrollRef}>
                          {sqlStreamingText || ' '}
                          {activeStreamingStage === 'sql' && <StreamCursor $color="#ffd700" />}
                        </StreamBody>
                      </StreamBox>
                    </AiBubble>
                  )}
                  <div ref={bottomRef} />
                </MessagesInner>
              </MessagesArea>
            )}

            {/* ═══ Input Bar ═══ */}
            <InputBar>
              <InputRow>
                <StyledInput
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onPressEnter={() => sendMessage()}
                  placeholder="Ask a question about your data..."
                  size="large"
                  disabled={loading}
                />
                <SendBtn
                  onClick={() => sendMessage()}
                  disabled={loading || !input.trim()}
                  $loading={loading}
                >
                  {loading ? <IconLoading /> : <IconSend />}
                </SendBtn>
              </InputRow>
            </InputBar>
          </ChatWrapper>
        </SiderLayout>
      </RequireConnection>

      {/* ═══ Thought Drawer — portal to document.body to escape all stacking contexts ═══ */}
      {mounted && createPortal(
        <>
          <DrawerOverlay $open={drawerOpen} onClick={() => setDrawerOpen(false)} />
          <DrawerPanel $open={drawerOpen}>
            <DrawerHeader>
              <DrawerTitle>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <svg width="14" height="14" viewBox="0 0 12 12" fill="none"><polygon points="7,1 3,7 6,7 5,11 9,5 6,5" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="miter" /></svg>
                  Pipeline Reasoning
                </span>
              </DrawerTitle>
              <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--m-black)', opacity: 0.6 }}>
                {drawerSeconds}s
              </span>
              <DrawerClose onClick={() => setDrawerOpen(false)}>✕</DrawerClose>
            </DrawerHeader>

            <DrawerBody>
              {drawerTrace && drawerTrace.stages && drawerTrace.stages.length > 0 ? (
                <DebugTracePanel trace={drawerTrace} />
              ) : (
                <div style={{
                  padding: '20px',
                  textAlign: 'center',
                  color: '#888',
                  fontFamily: 'Space Grotesk, sans-serif',
                  fontSize: 12,
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}>
                  Không có pipeline trace
                </div>
              )}
            </DrawerBody>

            <DrawerFooter>
              <span style={{ color: 'var(--m-pink)' }}>✓</span>
              {drawerTrace?.stages?.length ?? 0} stages completed in {drawerSeconds}s
            </DrawerFooter>
          </DrawerPanel>
        </>,
        document.body
      )}
    </>
  );
}
