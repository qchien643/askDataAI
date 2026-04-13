import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import Head from 'next/head';
import styled, { keyframes } from 'styled-components';
import { Input, Button, Table, Switch, Tooltip, message } from 'antd';
import SiderLayout from '@/components/layouts/SiderLayout';
import RequireConnection from '@/components/guards/RequireConnection';
import DebugTracePanel from '@/components/debug/DebugTracePanel';
import VegaChart from '@/components/VegaChart';
import { api } from '@/hooks/useApi';
import type { ProgressEvent } from '@/hooks/useApi';
import { useChat } from '@/contexts/ChatContext';
import type { Msg, Thread } from '@/contexts/ChatContext';
import type { DebugTrace } from '@/utils/types';

/* ═══════════════════════════════════════════════
   MEMPHIS SVG ICON COMPONENTS — no external deps
   Bold geometry, black borders, Memphis palette
   ═══════════════════════════════════════════════ */
const IconSend = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
    <polygon points="2,2 14,8 2,14 5,8" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.5" strokeLinejoin="miter"/>
    <line x1="5" y1="8" x2="13" y2="8" stroke="#0D0D0D" strokeWidth="1.5" strokeLinecap="square"/>
  </svg>
);
const IconLoading = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"
    style={{ animation: 'memSpin 0.8s steps(8,end) infinite' }}>
    <style>{`@keyframes memSpin { to { transform: rotate(360deg); } }`}</style>
    <rect x="7" y="1" width="2" height="4" fill="#FF3366"/>
    <rect x="7" y="11" width="2" height="4" opacity="0.25" fill="#FF3366"/>
    <rect x="1" y="7" width="4" height="2" opacity="0.5" fill="#FF3366"/>
    <rect x="11" y="7" width="4" height="2" opacity="0.25" fill="#FF3366"/>
    <rect x="3" y="3" width="2" height="2" opacity="0.75" fill="#FF3366" transform="rotate(45 4 4)"/>
    <rect x="11" y="3" width="2" height="2" opacity="0.4" fill="#FF3366" transform="rotate(45 12 4)"/>
  </svg>
);
const IconBug = ({ active }: { active: boolean }) => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="1" y="1" width="12" height="12"
      fill={active ? '#FF3366' : 'none'}
      stroke={active ? '#FF3366' : '#888'} strokeWidth="1.5"/>
    <line x1="4" y1="4" x2="10" y2="10" stroke={active ? '#FAFAF5' : '#888'} strokeWidth="1.5" strokeLinecap="square"/>
    <line x1="10" y1="4" x2="4" y2="10" stroke={active ? '#FAFAF5' : '#888'} strokeWidth="1.5" strokeLinecap="square"/>
  </svg>
);
const IconChart = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="1" y="8" width="3" height="5" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1.2"/>
    <rect x="5.5" y="5" width="3" height="8" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2"/>
    <rect x="10" y="2" width="3" height="11" fill="#00D4FF" stroke="#0D0D0D" strokeWidth="1.2"/>
    <line x1="1" y1="13" x2="13" y2="13" stroke="#0D0D0D" strokeWidth="1.5" strokeLinecap="square"/>
  </svg>
);

/* ── Stage icon map — Memphis SVG per pipeline stage ─────────────────────
   Each icon: 16×16 viewBox, bold 1.5px stroke, distinct Memphis color fill
   ──────────────────────────────────────────────────────────────────────── */
const StageIcons: Record<string, JSX.Element> = {
  /* start — lightning bolt */
  start: (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><polygon points="7,1 3,7 6,7 5,11 9,5 6,5" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="miter"/></svg>
  ),
  /* 0 — shield/guard */
  '0': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1 L11 3 L11 7 C11 9.5 6 11 6 11 C6 11 1 9.5 1 7 L1 3 Z" fill="#00D4FF" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="round"/><line x1="4" y1="6" x2="5.5" y2="8" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square"/><line x1="5.5" y1="8" x2="8" y2="4.5" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square"/></svg>
  ),
  /* 0.5 — speech bubble */
  '0.5': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="10" height="7" rx="0" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1.2"/><polygon points="3,8 3,11 6,8" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1" strokeLinejoin="miter"/><line x1="3" y1="4" x2="9" y2="4" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square"/><line x1="3" y1="6" x2="7" y2="6" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square"/></svg>
  ),
  /* 1 — funnel / classify */
  '1': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><polygon points="1,2 11,2 7,6 7,10 5,10 5,6" fill="#FF6B35" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="miter"/></svg>
  ),
  /* 2 — book / rules */
  '2': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="9" height="10" fill="#7B2FFF" stroke="#0D0D0D" strokeWidth="1.2"/><rect x="3" y="3" width="5" height="1.2" fill="#FAFAF5"/><rect x="3" y="5.5" width="5" height="1.2" fill="#FAFAF5"/><rect x="3" y="8" width="3.5" height="1.2" fill="#FAFAF5"/></svg>
  ),
  /* 3 — brain/analyze */
  '3': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><ellipse cx="6" cy="6" rx="5" ry="4" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2"/><line x1="4" y1="4" x2="4" y2="8" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square"/><line x1="6" y1="3" x2="6" y2="9" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square"/><line x1="8" y1="4" x2="8" y2="8" stroke="#0D0D0D" strokeWidth="1" strokeLinecap="square"/></svg>
  ),
  /* 4 — target/sub-intent */
  '4': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="5" fill="none" stroke="#0D0D0D" strokeWidth="1.2"/><circle cx="6" cy="6" r="3" fill="none" stroke="#0D0D0D" strokeWidth="1.2"/><circle cx="6" cy="6" r="1.5" fill="#FF3366"/></svg>
  ),
  /* 5 — magnify/search */
  '5': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="5" cy="5" r="3.5" fill="#00E676" stroke="#0D0D0D" strokeWidth="1.2"/><line x1="8" y1="8" x2="11" y2="11" stroke="#0D0D0D" strokeWidth="1.8" strokeLinecap="square"/></svg>
  ),
  /* 6 — chain links */
  '6': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="4" width="5" height="3" rx="1.5" fill="none" stroke="#0D0D0D" strokeWidth="1.3"/><rect x="6" y="5" width="5" height="3" rx="1.5" fill="none" stroke="#0D0D0D" strokeWidth="1.3"/><line x1="5" y1="5.5" x2="7" y2="6.5" stroke="#0D0D0D" strokeWidth="1"/><rect x="1" y="4" width="5" height="3" rx="1.5" fill="#00D4FF" opacity="0.6" stroke="none"/><rect x="6" y="5" width="5" height="3" rx="1.5" fill="#FF3366" opacity="0.6" stroke="none"/></svg>
  ),
  /* 7 — scissors/prune */
  '7': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="3" cy="4" r="2" fill="none" stroke="#0D0D0D" strokeWidth="1.2"/><circle cx="3" cy="8" r="2" fill="none" stroke="#0D0D0D" strokeWidth="1.2"/><line x1="5" y1="5" x2="11" y2="2" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square"/><line x1="5" y1="7" x2="11" y2="10" stroke="#0D0D0D" strokeWidth="1.2" strokeLinecap="square"/><circle cx="3" cy="4" r="1" fill="#FF6B35"/><circle cx="3" cy="8" r="1" fill="#FF6B35"/></svg>
  ),
  /* 8 — database/DDL */
  '8': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><ellipse cx="6" cy="3" rx="4.5" ry="2" fill="#C6FF00" stroke="#0D0D0D" strokeWidth="1.2"/><path d="M1.5 3 L1.5 9 C1.5 10.1 3.5 11 6 11 C8.5 11 10.5 10.1 10.5 9 L10.5 3" fill="none" stroke="#0D0D0D" strokeWidth="1.2"/><ellipse cx="6" cy="6" rx="4.5" ry="2" fill="none" stroke="#0D0D0D" strokeWidth="1" strokeDasharray="2,2"/></svg>
  ),
  /* 9 — dictionary */
  '9': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="2" y="1" width="8" height="10" fill="#7B2FFF" stroke="#0D0D0D" strokeWidth="1.2"/><rect x="2" y="1" width="2" height="10" fill="#0D0D0D"/><line x1="5" y1="4" x2="9" y2="4" stroke="#FAFAF5" strokeWidth="1"/><line x1="5" y1="6" x2="9" y2="6" stroke="#FAFAF5" strokeWidth="1"/><line x1="5" y1="8" x2="7.5" y2="8" stroke="#FAFAF5" strokeWidth="1"/></svg>
  ),
  /* 10 — memory/history */
  '10': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="5" fill="#00BFA5" stroke="#0D0D0D" strokeWidth="1.2"/><polyline points="6,3 6,6 8.5,8" fill="none" stroke="#0D0D0D" strokeWidth="1.3" strokeLinecap="square"/></svg>
  ),
  /* 11 — steps/CoT */
  '11': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="8" width="3" height="3" fill="#FF3366" stroke="#0D0D0D" strokeWidth="1"/><rect x="4.5" y="5" width="3" height="6" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1"/><rect x="8" y="2" width="3" height="9" fill="#00D4FF" stroke="#0D0D0D" strokeWidth="1"/></svg>
  ),
  /* 12 — lightning/generate */
  '12': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><polygon points="7,1 2.5,7 5.5,7 5,11 9.5,5 6.5,5" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="miter"/></svg>
  ),
  /* 13 / 13.5 / 14 — checkmark/done */
  '13': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="10" height="10" fill="#00E676" stroke="#0D0D0D" strokeWidth="1.2"/><polyline points="3,6 5,8.5 9,3.5" fill="none" stroke="#0D0D0D" strokeWidth="1.8" strokeLinecap="square" strokeLinejoin="miter"/></svg>
  ),
  '13.5': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="10" height="10" fill="#00E676" stroke="#0D0D0D" strokeWidth="1.2"/><polyline points="3,6 5,8.5 9,3.5" fill="none" stroke="#0D0D0D" strokeWidth="1.8" strokeLinecap="square" strokeLinejoin="miter"/></svg>
  ),
  '14': (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="1" width="10" height="10" fill="#00E676" stroke="#0D0D0D" strokeWidth="1.2"/><polyline points="3,6 5,8.5 9,3.5" fill="none" stroke="#0D0D0D" strokeWidth="1.8" strokeLinecap="square" strokeLinejoin="miter"/></svg>
  ),
};

/** Strip leading emoji/symbols from backend label strings */
const stripEmoji = (s: string) =>
  s.replace(/^[\u{1F000}-\u{1FFFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u00A9\u00AE\u{1F004}-\u{1F0CF}\u{1F3FB}-\u{1F9FF}\u2139\u203C\u2049\u{231A}-\u{231B}\u{2328}\u{23CF}\u{23E9}-\u{23F3}\u{23F8}-\u{23FA}\u{25AA}-\u{25AB}\u{25B6}\u{25C0}\u{25FB}-\u{25FE}\u{2600}-\u{2604}\u{260E}\u{2611}\u{2614}-\u{2615}\u{2618}\u{261D}\u{2620}\u{2622}-\u{2623}\u{2626}\u{262A}\u{262E}-\u{262F}\u{2638}-\u{263A}\u{2640}\u{2642}\u{2648}-\u{2653}\u{265F}-\u{2660}\u{2663}\u{2665}-\u{2666}\u{2668}\u{267B}\u{267E}-\u{267F}\u{2692}-\u{2697}\u{2699}\u{269B}-\u{269C}\u{26A0}-\u{26A1}\u{26AA}-\u{26AB}\u{26B0}-\u{26B1}\u{26BD}-\u{26BE}\u{26C4}-\u{26C5}\u{26CE}-\u{26CF}\u{26D1}\u{26D3}-\u{26D4}\u{26E9}-\u{26EA}\u{26F0}-\u{26F5}\u{26F7}-\u{26FA}\u{26FD}\u{2702}\u{2705}\u{2708}-\u{270D}\u{270F}\u{2712}\u{2714}\u{2716}\u{271D}\u{2721}\u{2728}\u{2733}-\u{2734}\u{2744}\u{2747}\u{274C}\u{274E}\u{2753}-\u{2755}\u{2757}\u{2763}-\u{2764}\u{2795}-\u{2797}\u{27A1}\u{27B0}\u{27BF}\u{2934}-\u{2935}\u{2B05}-\u{2B07}\u{2B1B}-\u{2B1C}\u{2B50}\u{2B55}\u{3030}\u{303D}\u{3297}\u{3299}⏳✅❌🛡️💭🔍📋🧠🎯📊🔗✂️🏗️📖💾🧩⚡??\s]+/u, '').trim();

/** Get the Memphis SVG icon for a given stage id */
const getStageIcon = (stage: string): JSX.Element =>
  StageIcons[stage] ?? StageIcons['12'];


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
const ProgressPanel = styled.div`
  border: 2px solid var(--m-black);
  box-shadow: 4px 4px 0 var(--m-black);
  background: var(--m-bg);
  padding: 12px 14px 10px;
  font-family: 'Space Grotesk', sans-serif;
  margin-bottom: 2px;
  animation: ${popIn} 0.2s ease;
  max-height: 380px;
  display: flex;
  flex-direction: column;
`;

const ProgressHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-shrink: 0;
`;

const ProgressTitle = styled.span`
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--m-black);
`;

const PipelineTrack = styled.div`
  height: 5px;
  background: var(--m-bg-2);
  border: 1.5px solid var(--m-black);
  position: relative;
  overflow: hidden;
  flex-shrink: 0;
  margin-bottom: 10px;
`;

const PipelineFill = styled.div<{ $pct: number }>`
  height: 100%;
  width: ${p => p.$pct}%;
  background: linear-gradient(90deg, var(--m-yellow), var(--m-pink), var(--m-cyan));
  transition: width 0.4s ease;
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

// 14 stages total (0, 0.5, 1..13, 13.5, 14) — map to 0-100%
const STAGE_PCT: Record<string, number> = {
  start: 2,
  '0':   8,
  '0.5': 14,
  '1':   20,
  '2':   26,
  '3':   33,
  '4':   40,
  '5':   47,
  '6':   53,
  '7':   59,
  '8':   65,
  '9':   71,
  '10':  76,
  '11':  82,
  '12':  88,
  '13':  92,
  '13.5': 96,
  '14':  99,
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
  width: 400px;
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
  padding: 16px 0;
`;

const SidebarLabel = styled.div`
  font-size: 10px;
  font-weight: 800;
  color: rgba(255,255,255,0.35);
  padding: 6px 16px;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  font-family: 'Space Grotesk', sans-serif;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  margin-bottom: 8px;
`;

const ThreadItem = styled.button<{ $active?: boolean }>`
  width: 100%;
  display: block;
  text-align: left;
  padding: 9px 16px;
  border: none;
  cursor: pointer;
  background: ${p => p.$active ? 'var(--m-yellow)' : 'transparent'};
  color: ${p => p.$active ? 'var(--m-black)' : 'rgba(255,255,255,0.65)'};
  font-size: 12px;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: ${p => p.$active ? '800' : '500'};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  border-left: ${p => p.$active ? '3px solid var(--m-pink)' : '3px solid transparent'};
  text-transform: uppercase;
  letter-spacing: 0.3px;
  transition: all 0.1s;

  &:hover {
    background: ${p => p.$active ? 'var(--m-yellow)' : 'rgba(255,230,0,0.08)'};
    color: ${p => p.$active ? 'var(--m-black)' : 'white'};
    border-left-color: rgba(255,230,0,0.5);
  }
`;

const NewThreadBtn = styled.button`
  width: calc(100% - 24px);
  margin: 4px 12px 12px;
  padding: 8px 12px;
  border: 2px dashed rgba(255,230,0,0.4);
  background: transparent;
  color: rgba(255,230,0,0.6);
  font-size: 11px;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    border-color: var(--m-yellow);
    color: var(--m-yellow);
    background: rgba(255,230,0,0.06);
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

/* ── User bubble ── */
const UserBubble = styled.div`
  align-self: flex-end;
  max-width: 66%;
  background: var(--m-black);
  color: white;
  padding: 12px 18px;
  border: 2px solid var(--m-black);
  box-shadow: 4px 4px 0 var(--m-pink);
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 600;
  font-size: 14px;
  line-height: 1.5;
  animation: ${slideInRight} 0.2s ease;
  position: relative;

  /* Memphis yellow corner accent */
  &::before {
    content: '';
    position: absolute;
    top: -4px; right: -4px;
    width: 12px; height: 12px;
    background: var(--m-yellow);
    border: 1.5px solid var(--m-black);
  }
`;

/* ── AI bubble ── */
const AiBubble = styled.div`
  align-self: flex-start;
  max-width: 92%;
  width: 100%;
  animation: ${popIn} 0.25s ease;
`;

/* ── AI card ── */
const AiCard = styled.div`
  background: white;
  border: 2px solid var(--m-black);
  box-shadow: var(--shadow-md);
  position: relative;
  overflow: visible;

  /* Memphis colored top border */
  &::before {
    content: '';
    position: absolute;
    top: -4px; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, var(--m-pink) 0%, var(--m-cyan) 50%, var(--m-yellow) 100%);
  }
`;

const AiCardHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1.5px solid var(--m-bg-3);
  background: var(--m-bg-2);
`;

const StatusDot = styled.span<{ $color: string }>`
  width: 9px; height: 9px;
  border-radius: 50%;
  background: ${p => p.$color};
  border: 1.5px solid var(--m-black);
  flex-shrink: 0;
`;

const AiCardTitle = styled.span`
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 800;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--m-black);
`;

const AiCardBody = styled.div`
  padding: 14px 16px;
`;

const ExplanationText = styled.p`
  font-size: 13px;
  color: #555;
  margin-bottom: 12px;
  font-style: italic;
  font-family: 'Space Grotesk', sans-serif;
  line-height: 1.6;
  border-left: 3px solid var(--m-cyan);
  padding-left: 10px;
`;

/* ── SQL block ── */
const SqlBlock = styled.pre`
  background: var(--m-black);
  color: #E8E6E0;
  border: 2px solid var(--m-black);
  padding: 14px 16px;
  font-size: 12.5px;
  line-height: 1.7;
  overflow-x: auto;
  margin: 10px 0 14px;
  font-family: 'JetBrains Mono', monospace;
  box-shadow: 3px 3px 0 var(--m-pink);
  position: relative;

  /* SQL label */
  &::before {
    content: 'SQL';
    position: absolute;
    top: 6px; right: 10px;
    font-size: 9px;
    font-weight: 900;
    font-family: 'Space Grotesk', sans-serif;
    letter-spacing: 2px;
    color: var(--m-yellow);
    opacity: 0.6;
  }
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

const WelcomeCard = styled.div`
  text-align: center;
  position: relative;
  z-index: 2;
`;

const WelcomeLogo = styled.div`
  width: 80px; height: 80px;
  background: var(--m-yellow);
  border: 3px solid var(--m-black);
  box-shadow: 6px 6px 0 var(--m-black);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
  font-weight: 900;
  font-family: 'Space Grotesk', sans-serif;
  color: var(--m-black);
  margin: 0 auto 20px;
  animation: ${floatShape} 4s ease-in-out infinite;
`;

const WelcomeTitle = styled.h1`
  font-size: 28px;
  font-weight: 900;
  font-family: 'Space Grotesk', sans-serif;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--m-black);
  margin-bottom: 12px;
  line-height: 1.1;

  span.pink { color: var(--m-pink); }
  span.cyan { color: var(--m-blue); }
`;

const WelcomeSub = styled.p`
  font-size: 13px;
  color: #777;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 600;
  margin-bottom: 32px;
  background: white;
  border: 1.5px solid var(--m-black);
  box-shadow: 2px 2px 0 var(--m-black);
  padding: 5px 16px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-size: 11px;
`;

const SampleQueries = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  max-width: 600px;
`;

const SampleBtn = styled.button`
  background: white;
  border: 2px solid var(--m-black);
  box-shadow: 3px 3px 0 var(--m-black);
  padding: 8px 16px;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 12px;
  font-weight: 700;
  color: var(--m-black);
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  transition: all 0.1s;

  &:hover {
    transform: translate(-2px, -2px);
    box-shadow: 5px 5px 0 var(--m-black);
    background: var(--m-yellow);
  }
  &:active {
    transform: translate(3px, 3px);
    box-shadow: none;
  }
`;

/* Memphis floating shapes in welcome */
const FloatShape = styled.div<{
  $type: 'circle' | 'square' | 'triangle';
  $color: string;
  $size: number;
  $top: string; $left: string;
  $delay?: number;
}>`
  position: absolute;
  top: ${p => p.$top};
  left: ${p => p.$left};
  width: ${p => p.$size}px;
  height: ${p => p.$size}px;
  background: ${p => p.$type !== 'triangle' ? p.$color : 'transparent'};
  border-radius: ${p => p.$type === 'circle' ? '50%' : '0'};
  border: ${p => p.$type !== 'triangle' ? `2px solid var(--m-black)` : 'none'};
  ${p => p.$type === 'triangle' ? `
    width: 0; height: 0;
    border-left: ${p.$size}px solid transparent;
    border-right: ${p.$size}px solid transparent;
    border-bottom: ${p.$size * 1.7}px solid ${p.$color};
    background: transparent;
  ` : ''}
  opacity: 0.7;
  animation: ${floatShape} ${p => 3 + (p.$delay || 0)}s ease-in-out infinite;
  animation-delay: ${p => p.$delay || 0}s;
  pointer-events: none;
`;

/* ════════════════════════════════════════════
   INPUT BAR
   ════════════════════════════════════════════ */
const InputBar = styled.div`
  border-top: 3px solid var(--m-black);
  padding: 14px 24px;
  background: white;
  position: relative;
  z-index: 10;

  /* Memphis top accent bar */
  &::before {
    content: '';
    position: absolute;
    top: -7px; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg,
      var(--m-yellow) 0%, var(--m-pink) 33%,
      var(--m-cyan) 66%, var(--m-orange) 100%
    );
  }
`;

const InputRow = styled.div`
  max-width: 820px;
  margin: 0 auto;
  display: flex;
  gap: 10px;
  align-items: center;
`;

const StyledInput = styled(Input)`
  && {
    border: 2px solid var(--m-black) !important;
    border-radius: 0 !important;
    background: var(--m-bg) !important;
    font-family: 'Space Grotesk', sans-serif !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    color: var(--m-black) !important;
    height: 46px !important;
    padding: 0 16px !important;
    box-shadow: 3px 3px 0 var(--m-black) !important;
    transition: box-shadow 0.1s, border-color 0.1s !important;

    &::placeholder {
      color: #999 !important;
      font-weight: 500 !important;
      font-size: 13px !important;
    }

    &:focus {
      border-color: var(--m-pink) !important;
      box-shadow: 3px 3px 0 var(--m-pink) !important;
      background: white !important;
    }

    &:disabled {
      opacity: 0.6 !important;
    }
  }
`;

const SendBtn = styled.button<{ $loading?: boolean }>`
  width: 46px; height: 46px;
  background: var(--m-pink);
  border: 2px solid var(--m-black);
  box-shadow: 3px 3px 0 var(--m-black);
  color: white;
  cursor: ${p => p.$loading ? 'wait' : 'var(--cur-pointer)'};
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
  transition: all 0.1s;

  &:hover:not(:disabled) {
    transform: translate(-2px, -2px);
    box-shadow: 5px 5px 0 var(--m-black);
    background: #e0002c;
  }
  &:active {
    transform: translate(3px, 3px);
    box-shadow: none;
  }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
`;

const DebugToggle = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  font-family: 'Space Grotesk', sans-serif;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: ${(props: any) => props.active ? 'var(--m-pink)' : '#aaa'};
  flex-shrink: 0;
  padding: 0 4px;
`;

/* ══════════════════════════════════════════════
   MAIN COMPONENT
   ══════════════════════════════════════════════ */
export default function HomePage() {
  const { threads, setThreads, activeId, setActiveId } = useChat();
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const [pipelineSteps, setPipelineSteps] = useState<ProgressEvent[]>([]);
  // Thought drawer state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerSteps, setDrawerSteps] = useState<{ stage: string; label: string; detail?: string }[]>([]);
  const [drawerSeconds, setDrawerSeconds] = useState(0);
  const startTimeRef = useRef<number>(0);
  // Accumulator ref — avoids stale closure when reading steps after await
  const stepsAccRef = useRef<ProgressEvent[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  // mounted guard for createPortal (Next.js SSR safe)
  const [mounted, setMounted] = useState(false);

  const active = threads.find(t => t.id === activeId);

  useEffect(() => { setMounted(true); }, []);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [active?.messages.length]);

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
    } catch (err: any) {
      message.error(err.message || 'Failed to connect to API server');
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
        ? { ...t, messages: t.messages.map((m, i) =>
            i === msgIndex ? { ...m, chartLoading: true, chartError: undefined } : m
          )}
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
      <NewThreadBtn onClick={newThread}>+ New Conversation</NewThreadBtn>
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
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" style={{ display:'inline',verticalAlign:'middle',marginRight:3 }}><circle cx="3" cy="4" r="2" fill="none" stroke="currentColor" strokeWidth="1.2"/><circle cx="3" cy="8" r="2" fill="none" stroke="currentColor" strokeWidth="1.2"/><line x1="5" y1="5" x2="11" y2="2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="square"/><line x1="5" y1="7" x2="11" y2="10" stroke="currentColor" strokeWidth="1.2" strokeLinecap="square"/></svg>
            {info.columns_pruned} cols
          </Chip>
        )}
        {info.glossary_matches != null && info.glossary_matches > 0 && (
          <Chip $bg="var(--m-green)" $color="var(--m-black)">
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" style={{ display:'inline',verticalAlign:'middle',marginRight:3 }}><rect x="2" y="1" width="8" height="10" fill="none" stroke="currentColor" strokeWidth="1.2"/><rect x="2" y="1" width="2" height="10" fill="currentColor"/><line x1="5" y1="4" x2="9" y2="4" stroke="currentColor" strokeWidth="1"/><line x1="5" y1="6" x2="9" y2="6" stroke="currentColor" strokeWidth="1"/></svg>
            {info.glossary_matches} glossary
          </Chip>
        )}
        {info.guardian_passed === false && (
          <Chip $bg="var(--m-red)" $color="white">
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" style={{ display:'inline',verticalAlign:'middle',marginRight:3 }}><path d="M6 1 L11 3 L11 7 C11 9.5 6 11 6 11 C6 11 1 9.5 1 7 L1 3 Z" fill="none" stroke="white" strokeWidth="1.2"/><line x1="4" y1="4" x2="8" y2="8" stroke="white" strokeWidth="1.2"/><line x1="8" y1="4" x2="4" y2="8" stroke="white" strokeWidth="1.2"/></svg>
            Blocked
          </Chip>
        )}
        {info.reasoning_steps && info.reasoning_steps.length > 0 && (
          <Chip $bg="var(--m-purple)" $color="white">
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" style={{ display:'inline',verticalAlign:'middle',marginRight:3 }}><rect x="1" y="8" width="3" height="3" fill="white" stroke="white" strokeWidth="0.5"/><rect x="4.5" y="5" width="3" height="6" fill="white" stroke="white" strokeWidth="0.5"/><rect x="8" y="2" width="3" height="9" fill="white" stroke="white" strokeWidth="0.5"/></svg>
            {info.reasoning_steps.length} steps
          </Chip>
        )}
        {info.was_enriched && info.enriched_question && (
          <Tooltip title={`Câu hỏi được diễn giải: "${info.enriched_question}"`}>
            <Chip $bg="var(--m-orange)" $color="white">
              <svg width="10" height="10" viewBox="0 0 12 12" fill="none" style={{ display:'inline',verticalAlign:'middle',marginRight:3 }}><rect x="1" y="1" width="10" height="7" fill="none" stroke="white" strokeWidth="1.2"/><polygon points="3,8 3,11 6,8" fill="white"/></svg>
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
              {/* Memphis floating shapes */}
              <FloatShape $type="circle" $color="var(--m-pink)" $size={40} $top="8%" $left="6%" $delay={0} />
              <FloatShape $type="square" $color="var(--m-yellow)" $size={30} $top="15%" $left="88%" $delay={1} />
              <FloatShape $type="triangle" $color="var(--m-cyan)" $size={22} $top="72%" $left="8%" $delay={0.5} />
              <FloatShape $type="circle" $color="var(--m-orange)" $size={20} $top="78%" $left="90%" $delay={1.5} />
              <FloatShape $type="square" $color="var(--m-purple)" $size={18} $top="30%" $left="3%" $delay={2} />
              <FloatShape $type="circle" $color="var(--m-green)" $size={14} $top="60%" $left="94%" $delay={0.8} />
              <FloatShape $type="triangle" $color="var(--m-pink)" $size={16} $top="20%" $left="14%" $delay={1.2} />
              <FloatShape $type="square" $color="var(--m-cyan)" $size={25} $top="85%" $left="50%" $delay={0.3} />

              <WelcomeCard>
                <WelcomeLogo>A</WelcomeLogo>
                <WelcomeTitle>
                  Ask your <span className="pink">Data</span><br />
                  Get <span className="cyan">SQL</span> instantly
                </WelcomeTitle>
                <WelcomeSub>
                  askDataAI · Multi-turn context aware · Text-to-SQL
                </WelcomeSub>
                <SampleQueries>
                  {samples.map(s => (
                    <SampleBtn key={s} onClick={() => sendMessage(s)}>{s}</SampleBtn>
                  ))}
                </SampleQueries>
              </WelcomeCard>
            </WelcomeArea>
          ) : (
            /* ═══ Messages ═══ */
            <MessagesArea>
              <MessagesInner>
                {active.messages.map((msg, i) =>
                  msg.role === 'user' ? (
                    <UserBubble key={i}>{msg.text}</UserBubble>
                  ) : (
                    <AiBubble key={i}>
                      <AiCard>
                        <AiCardHeader>
                          <StatusDot $color={msg.valid ? 'var(--m-green)' : 'var(--m-red)'} />
                          <AiCardTitle>{msg.valid ? 'Query Result' : 'Error'}</AiCardTitle>
                        </AiCardHeader>
                        <AiCardBody>
                          {/* Thought chip — show if message has pipeline steps */}
                          {msg.thoughtSteps && msg.thoughtSteps.length > 0 && (
                            <ThoughtBtn
                              onClick={() => {
                                setDrawerSteps(msg.thoughtSteps!);
                                setDrawerSeconds(msg.thoughtSeconds ?? 0);
                                setDrawerOpen(true);
                              }}
                            >
                              ⚡ Thought for {msg.thoughtSeconds ?? 0}s
                            </ThoughtBtn>
                          )}
                          {msg.explanation && (
                            <ExplanationText>{msg.explanation}</ExplanationText>
                          )}
                          {msg.pipelineInfo && renderPipelineInfo(msg.pipelineInfo)}
                          {msg.sql && <SqlBlock>{msg.sql}</SqlBlock>}

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

                          {/* Debug trace */}
                          {msg.debugTrace && msg.debugTrace.stages && msg.debugTrace.stages.length > 0 && (
                            <DebugTracePanel trace={msg.debugTrace} />
                          )}
                        </AiCardBody>
                      </AiCard>
                    </AiBubble>
                  )
                )}

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
                      <LiveStepList>
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
              <Tooltip title={debugMode ? 'Debug ON — pipeline trace visible' : 'Enable debug mode'}>
                <DebugToggle active={debugMode}>
                  <IconBug active={debugMode} />
                  <Switch
                    size="small"
                    checked={debugMode}
                    onChange={setDebugMode}
                  />
                </DebugToggle>
              </Tooltip>
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
                <svg width="14" height="14" viewBox="0 0 12 12" fill="none"><polygon points="7,1 3,7 6,7 5,11 9,5 6,5" fill="#FFE600" stroke="#0D0D0D" strokeWidth="1.2" strokeLinejoin="miter"/></svg>
                Pipeline Reasoning
              </span>
            </DrawerTitle>
            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--m-black)', opacity: 0.6 }}>
              {drawerSeconds}s
            </span>
            <DrawerClose onClick={() => setDrawerOpen(false)}>✕</DrawerClose>
          </DrawerHeader>

          <DrawerBody>
            {drawerSteps.map((step, idx) => (
              <ThoughtStepRow key={idx} $last={idx === drawerSteps.length - 1}>
                <ThoughtDot $done={true} title={`Stage ${step.stage}`}>
                  {getStageIcon(step.stage)}
                </ThoughtDot>
                <ThoughtContent>
                  <ThoughtLabel>
                    {stripEmoji(step.label)}
                    <ThoughtStageId>· {step.stage}</ThoughtStageId>
                  </ThoughtLabel>
                  {step.detail && (
                    <ThoughtDetail>{stripEmoji(step.detail)}</ThoughtDetail>
                  )}
                </ThoughtContent>
              </ThoughtStepRow>
            ))}
          </DrawerBody>

          <DrawerFooter>
            <span style={{ color: 'var(--m-pink)' }}>✓</span>
            {drawerSteps.length} stages completed in {drawerSeconds}s
          </DrawerFooter>
        </DrawerPanel>
      </>,
      document.body
    )}
    </>
  );
}
