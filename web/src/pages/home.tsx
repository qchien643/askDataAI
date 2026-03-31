import { useState, useRef, useEffect } from 'react';
import Head from 'next/head';
import styled from 'styled-components';
import { Input, Button, Table, Switch, Tooltip, message } from 'antd';
import { SendOutlined, BugOutlined, BarChartOutlined, LoadingOutlined } from '@ant-design/icons';
import SiderLayout from '@/components/layouts/SiderLayout';
import RequireConnection from '@/components/guards/RequireConnection';
import DebugTracePanel from '@/components/debug/DebugTracePanel';
import VegaChart from '@/components/VegaChart';
import { api } from '@/hooks/useApi';
import { useChat } from '@/contexts/ChatContext';
import type { Msg, Thread } from '@/contexts/ChatContext';
import type { DebugTrace } from '@/utils/types';


/* ── Sidebar ── */
const SidebarSection = styled.div`padding: 12px 0;`;
const SidebarLabel = styled.div`
  font-size: 12px; font-weight: 700; color: #434343;
  padding: 5px 16px; text-transform: uppercase; letter-spacing: 0.5px;
`;
const ThreadItem = styled.button<{ $active?: boolean }>`
  width: 100%; display: block; text-align: left;
  padding: 8px 16px; border: none; cursor: pointer;
  background: ${p => p.$active ? '#d9d9d9' : 'transparent'};
  color: #434343; font-size: 13px; font-family: inherit;
  font-weight: ${p => p.$active ? 500 : 400};
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  &:hover { background: ${p => p.$active ? '#d9d9d9' : '#f0f0f0'}; }
`;
const NewThreadBtn = styled.button`
  width: calc(100% - 24px); margin: 8px 12px;
  padding: 6px; border: 1px dashed #d9d9d9; border-radius: 4px;
  background: transparent; color: #8c8c8c; font-size: 13px;
  cursor: pointer; font-family: inherit;
  &:hover { border-color: #4B6BFB; color: #4B6BFB; }
`;

/* ── Chat Area ── */
const ChatWrapper = styled.div`
  display: flex; flex-direction: column; height: 100%;
`;
const MessagesArea = styled.div`
  flex: 1; overflow-y: auto; padding: 24px;
  display: flex; flex-direction: column;
`;
const MessagesInner = styled.div`
  max-width: 800px; width: 100%; margin: 0 auto;
  display: flex; flex-direction: column; gap: 20px;
`;
const UserBubble = styled.div`
  align-self: flex-end; max-width: 70%;
  background: #f5f5f5; border-radius: 12px 12px 2px 12px;
  padding: 10px 16px; font-size: 14px; color: #262626;
`;
const AiBubble = styled.div`
  align-self: flex-start; max-width: 90%; width: 100%;
`;
const StatusBadge = styled.div`
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 13px; color: #434343; margin-bottom: 8px;
`;
const Dot = styled.span<{ $color: string }>`
  width: 8px; height: 8px; border-radius: 50%;
  background: ${p => p.$color}; display: inline-block;
`;
const SqlBlock = styled.pre`
  background: #1f1f1f; color: #e6e6e6; border-radius: 4px;
  padding: 12px 16px; font-size: 13px; line-height: 1.6;
  overflow-x: auto; margin: 8px 0 12px;
  font-family: 'JetBrains Mono', monospace;
`;
const ExplanationText = styled.p`
  font-size: 13px; color: #65676c; margin-bottom: 12px;
  font-style: italic;
`;

/* ── Pipeline Info ── */
const PipelineInfoBar = styled.div`
  display: flex; flex-wrap: wrap; gap: 8px;
  margin: 8px 0;
`;

const InfoChip = styled.span<{ $variant?: 'default' | 'success' | 'warning' | 'error' }>`
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
  ${p => {
    switch (p.$variant) {
      case 'success': return 'color: #389e0d; background: #f6ffed; border: 1px solid #b7eb8f;';
      case 'warning': return 'color: #d48806; background: #fffbe6; border: 1px solid #ffe58f;';
      case 'error': return 'color: #cf1322; background: #fff2f0; border: 1px solid #ffccc7;';
      default: return 'color: #434343; background: #f5f5f5; border: 1px solid #e8e8e8;';
    }
  }}
`;

/* ── Input Bar ── */
const InputBar = styled.div`
  border-top: 1px solid #f0f0f0; padding: 12px 24px;
  background: white;
`;
const InputRow = styled.div`
  max-width: 800px; margin: 0 auto;
  display: flex; gap: 8px; align-items: center;
`;

const DebugToggle = styled.div`
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #8c8c8c;
  flex-shrink: 0;
`;

const WelcomeArea = styled.div`
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  color: #8c8c8c; font-size: 16px;
`;
const WelcomeIcon = styled.div`
  width: 64px; height: 64px; background: #f0f5ff;
  border-radius: 16px; display: flex; align-items: center;
  justify-content: center; font-size: 28px; margin-bottom: 16px;
  color: #4B6BFB; font-weight: 700;
`;



export default function HomePage() {
  const { threads, setThreads, activeId, setActiveId } = useChat();
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [debugMode, setDebugMode] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const active = threads.find(t => t.id === activeId);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [active?.messages.length]);

  const newThread = () => {
    const id = Date.now().toString();
    const t: Thread = { id, title: 'New conversation', messages: [] };
    setThreads(prev => [t, ...prev]);
    setActiveId(id);
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const question = input.trim();
    setInput('');

    let tid = activeId;
    if (!tid) {
      const id = Date.now().toString();
      const t: Thread = { id, title: question.slice(0, 40), messages: [] };
      setThreads(prev => [t, ...prev]);
      setActiveId(id);
      tid = id;
    }

    // Add user message
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
    try {
      const res = await api.ask(question, undefined, debugMode);
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
        } : undefined,
        debugTrace: res.debug_trace,
        originalQuestion: question,
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

    // Set chart loading
    setThreads(prev => prev.map(t =>
      t.id === active.id
        ? {
          ...t,
          messages: t.messages.map((m, i) =>
            i === msgIndex ? { ...m, chartLoading: true, chartError: undefined } : m
          ),
        }
        : t
    ));

    try {
      const res = await api.generateChart(msg.originalQuestion, msg.sql);
      setThreads(prev => prev.map(t =>
        t.id === active.id
          ? {
            ...t,
            messages: t.messages.map((m, i) =>
              i === msgIndex
                ? {
                  ...m,
                  chartLoading: false,
                  chartSpec: res.chart_schema,
                  chartData: res.data?.rows || m.rows,
                  chartReasoning: res.reasoning,
                  chartType: res.chart_type,
                  chartError: res.error || undefined,
                }
                : m
            ),
          }
          : t
      ));
    } catch (err: any) {
      setThreads(prev => prev.map(t =>
        t.id === active.id
          ? {
            ...t,
            messages: t.messages.map((m, i) =>
              i === msgIndex
                ? { ...m, chartLoading: false, chartError: err.message || 'Chart generation failed' }
                : m
            ),
          }
          : t
      ));
    }
  };

  const sidebar = (
    <SidebarSection>
      <SidebarLabel>Threads</SidebarLabel>
      <NewThreadBtn onClick={newThread}>+ New conversation</NewThreadBtn>
      {threads.map(t => (
        <ThreadItem key={t.id} $active={t.id === activeId} onClick={() => setActiveId(t.id)}>
          {t.title}
        </ThreadItem>
      ))}
    </SidebarSection>
  );

  const renderTable = (columns: string[], rows: any[]) => {
    const cols = columns.map(c => ({
      title: c,
      dataIndex: c,
      key: c,
      ellipsis: true,
      render: (v: any) => <span style={{ fontSize: 13 }}>{v != null ? String(v) : '-'}</span>,
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

  const renderPipelineInfo = (info: Msg['pipelineInfo']) => {
    if (!info) return null;
    return (
      <PipelineInfoBar>
        {info.sub_intent && (
          <InfoChip $variant="default">🎯 {info.sub_intent}</InfoChip>
        )}
        {info.candidates_generated != null && info.candidates_generated > 0 && (
          <InfoChip $variant="default">🗳 {info.candidates_generated} candidates · {info.voting_method}</InfoChip>
        )}
        {info.columns_pruned != null && info.columns_pruned > 0 && (
          <InfoChip $variant="default">✂ {info.columns_pruned} cols pruned</InfoChip>
        )}
        {info.glossary_matches != null && info.glossary_matches > 0 && (
          <InfoChip $variant="success">📖 {info.glossary_matches} glossary</InfoChip>
        )}
        {info.guardian_passed === false && (
          <InfoChip $variant="error">🛡 Guardian blocked</InfoChip>
        )}

        {info.reasoning_steps && info.reasoning_steps.length > 0 && (
          <InfoChip $variant="default">🧠 {info.reasoning_steps.length} reasoning steps</InfoChip>
        )}
      </PipelineInfoBar>
    );
  };

  return (
    <RequireConnection>
      <Head><title>Home — Mini Wren AI</title></Head>
      <SiderLayout sidebar={sidebar}>
        <ChatWrapper>
          {!active || active.messages.length === 0 ? (
            <WelcomeArea>
              <WelcomeIcon>W</WelcomeIcon>
              <div style={{ fontSize: 18, color: '#262626', fontWeight: 500, marginBottom: 8 }}>
                Ask a question about your data
              </div>
              <div style={{ fontSize: 14, color: '#8c8c8c' }}>
                Mini Wren AI will generate SQL and show results
              </div>
            </WelcomeArea>
          ) : (
            <MessagesArea>
              <MessagesInner>
                {active.messages.map((msg, i) => (
                  msg.role === 'user' ? (
                    <UserBubble key={i}>{msg.text}</UserBubble>
                  ) : (
                    <AiBubble key={i}>
                      <StatusBadge>
                        <Dot $color={msg.valid ? '#52c41a' : '#ff4d4f'} />
                        {msg.text}
                      </StatusBadge>
                      {msg.explanation && <ExplanationText>{msg.explanation}</ExplanationText>}
                      {msg.pipelineInfo && renderPipelineInfo(msg.pipelineInfo)}
                      {msg.sql && <SqlBlock>{msg.sql}</SqlBlock>}
                      {msg.columns && msg.rows && msg.rows.length > 0 && (
                        <>
                          <div style={{ fontSize: 13, color: '#8c8c8c', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span>{msg.rowCount} rows returned</span>
                            {msg.sql && !msg.chartSpec && !msg.chartLoading && (
                              <Tooltip title="Tạo biểu đồ từ kết quả">
                                <Button
                                  size="small"
                                  icon={<BarChartOutlined />}
                                  onClick={() => generateChart(i)}
                                  style={{ fontSize: 12 }}
                                >
                                  Tạo biểu đồ
                                </Button>
                              </Tooltip>
                            )}
                            {msg.chartLoading && (
                              <span style={{ color: '#4B6BFB', fontSize: 12 }}>
                                <LoadingOutlined style={{ marginRight: 4 }} />
                                Đang tạo biểu đồ...
                              </span>
                            )}
                          </div>
                          {renderTable(msg.columns, msg.rows)}
                        </>
                      )}
                      {msg.chartSpec && Object.keys(msg.chartSpec).length > 0 && (
                        <VegaChart
                          spec={msg.chartSpec}
                          data={msg.chartData}
                          reasoning={msg.chartReasoning}
                          chartType={msg.chartType}
                        />
                      )}
                      {msg.chartError && !msg.chartLoading && (
                        <div style={{ color: '#cf1322', fontSize: 13, marginTop: 8, padding: '6px 12px', background: '#fff2f0', borderRadius: 4, border: '1px solid #ffccc7' }}>
                          ⚠ Chart error: {msg.chartError}
                        </div>
                      )}
                      {msg.debugTrace && msg.debugTrace.stages && msg.debugTrace.stages.length > 0 && (
                        <DebugTracePanel trace={msg.debugTrace} />
                      )}
                    </AiBubble>
                  )
                ))}
                {loading && (
                  <AiBubble>
                    <StatusBadge>
                      <Dot $color="#faad14" />
                      Generating SQL...
                    </StatusBadge>
                  </AiBubble>
                )}
                <div ref={bottomRef} />
              </MessagesInner>
            </MessagesArea>
          )}

          <InputBar>
            <InputRow>
              <Input
                value={input}
                onChange={e => setInput(e.target.value)}
                onPressEnter={sendMessage}
                placeholder="Ask a question about your data..."
                size="large"
                disabled={loading}
              />
              <Tooltip title={debugMode ? 'Debug mode ON — pipeline trace will be shown' : 'Enable debug mode to see pipeline stages'}>
                <DebugToggle>
                  <BugOutlined style={{ fontSize: 14, color: debugMode ? '#4B6BFB' : '#bfbfbf' }} />
                  <Switch
                    size="small"
                    checked={debugMode}
                    onChange={setDebugMode}
                  />
                </DebugToggle>
              </Tooltip>
              <Button
                type="primary"
                icon={<SendOutlined />}
                size="large"
                onClick={sendMessage}
                loading={loading}
              />
            </InputRow>
          </InputBar>
        </ChatWrapper>
      </SiderLayout>
    </RequireConnection>
  );
}
