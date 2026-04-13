import { useState, useEffect, useCallback } from 'react';
import Head from 'next/head';
import styled from 'styled-components';
import { Drawer, Table, Button, message, Typography, Tag, Input } from 'antd';
import { EditOutlined, SaveOutlined, CloseOutlined } from '@ant-design/icons';
import ReactFlow, {
  MiniMap, Controls, Background,
  useNodesState, useEdgesState,
  Position, Handle, MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';
import SiderLayout from '@/components/layouts/SiderLayout';
import RequireConnection from '@/components/guards/RequireConnection';
import { useConnection } from '@/contexts/ConnectionContext';
import { api } from '@/hooks/useApi';
import type { Model, Relationship } from '@/utils/types';

const { Text } = Typography;
const { TextArea } = Input;

/* ── Custom Node — Memphis ── */
const NodeWrapper = styled.div`
  width: 300px;
  border: 2px solid var(--m-black, #0D0D0D);
  border-radius: 0;
  overflow: visible;
  box-shadow: 4px 4px 0 var(--m-black, #0D0D0D);
  cursor: pointer;
  font-family: 'Space Grotesk', sans-serif;
  background: #fff;
  transition: transform 0.08s, box-shadow 0.08s;
  &:hover {
    transform: translate(-2px, -2px);
    box-shadow: 6px 6px 0 var(--m-black, #0D0D0D);
    outline: none;
  }
`;
const NodeHeader = styled.div<{ $color?: string }>`
  background: ${p => p.$color || 'var(--m-black, #0D0D0D)'};
  color: ${p => p.$color && p.$color !== 'var(--m-black, #0D0D0D)' ? '#0D0D0D' : 'var(--m-yellow, #FFE600)'};
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  border-bottom: 2px solid var(--m-black, #0D0D0D);
`;
const NodeBody = styled.div`
  background: white;
  padding: 4px 0;
  max-height: 320px;
  overflow-y: auto;
`;
const NodeSection = styled.div`
  font-size: 9px;
  color: #999;
  padding: 4px 10px 2px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  font-family: 'Space Grotesk', sans-serif;
`;
const NodeCol = styled.div<{ $isFk?: boolean }>`
  padding: 4px 10px;
  font-size: 12px;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: ${p => p.$isFk ? '700' : '500'};
  color: ${p => p.$isFk ? 'var(--m-blue, #2979FF)' : '#0D0D0D'};
  position: relative;
  &:hover { background: rgba(255,230,0,0.15); }
`;
const ColRow = styled.div`
  display: flex; align-items: center; gap: 4px;
`;
const ColDesc = styled.div`
  font-size: 10px;
  color: #aaa;
  margin-top: 1px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-style: italic;
`;
const ColType = styled.span`
  font-size: 9px;
  color: #999;
  margin-left: auto;
  flex-shrink: 0;
  font-family: 'JetBrains Mono', monospace;
  font-weight: 500;
  text-transform: uppercase;
`;

/* PK icon */
const PkIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="#faad14" stroke="#faad14" strokeWidth="1">
    <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
  </svg>
);

/* FK icon */
const FkIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#4B6BFB" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
  </svg>
);

function ModelNodeComponent({ data }: { data: any }) {
  const { model, fkColumns } = data;
  const fkSet = new Set(fkColumns || []);

  return (
    <NodeWrapper onClick={() => data.onNodeClick?.(model)}>
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: 'var(--m-yellow, #FFE600)', border: '2px solid #0D0D0D', borderRadius: 0, width: 10, height: 10 }}
      />
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: 'var(--m-yellow, #FFE600)', border: '2px solid #0D0D0D', borderRadius: 0, width: 10, height: 10 }}
      />
      <NodeHeader>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
        </svg>
        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {model.name}
        </span>
        <span style={{ fontSize: 10, opacity: 0.7 }}>{model.columns.length} cols</span>
      </NodeHeader>
      <NodeBody>
        <NodeSection>Columns</NodeSection>
        {model.columns.slice(0, 7).map((col: any) => {
          const isPk = col.name === model.primary_key;
          const isFk = fkSet.has(col.name);
          return (
            <NodeCol key={col.name} $isFk={isFk}>
              <ColRow>
                {isPk && <PkIcon />}
                {isFk && !isPk && <FkIcon />}
                <span style={{ fontWeight: isPk ? 600 : 400 }}>{col.display_name || col.name}</span>
                <ColType>{col.type}</ColType>
              </ColRow>
              {col.description && (
                <ColDesc title={col.description}>{col.description}</ColDesc>
              )}
            </NodeCol>
          );
        })}
        {model.columns.length > 7 && (
          <NodeCol style={{ color: '#8c8c8c', fontStyle: 'italic' }}>
            +{model.columns.length - 7} more
          </NodeCol>
        )}
      </NodeBody>
    </NodeWrapper>
  );
}

const nodeTypes = { modelNode: ModelNodeComponent };

/* ── Sidebar — Memphis ── */
const SidebarSection = styled.div`padding: 12px 0;`;
const SidebarLabel = styled.div`
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px;
  font-weight: 800;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  padding: 8px 16px 4px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  margin-bottom: 4px;
`;
const ModelItem = styled.button<{ $active?: boolean }>`
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border: none;
  border-left: ${p => p.$active ? '3px solid var(--m-yellow, #FFE600)' : '3px solid transparent'};
  cursor: pointer;
  background: ${p => p.$active ? 'rgba(255,230,0,0.12)' : 'transparent'};
  color: ${p => p.$active ? '#fff' : 'rgba(255,255,255,0.6)'};
  font-size: 12px;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: ${p => p.$active ? '700' : '500'};
  text-align: left;
  transition: all 0.1s;
  &:hover {
    background: rgba(255,230,0,0.08);
    color: #fff;
    border-left-color: rgba(255,230,0,0.4);
  }
`;

/* ── Metadata Drawer Content — Memphis ── */
const MetaRow = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 24px;
`;
const MetaField = styled.div``;
const MetaLabel = styled.div`
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px;
  font-weight: 800;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  margin-bottom: 6px;
`;
const MetaValue = styled.div`
  font-family: 'Space Grotesk', sans-serif;
  font-size: 14px;
  font-weight: 600;
  color: #0D0D0D;
`;

/* ── Helper: extract FK columns from relationship conditions ── */
function extractFkColumns(rels: Relationship[], modelName: string): string[] {
  const fkCols: string[] = [];
  for (const r of rels) {
    if (r.model_from === modelName || r.model_to === modelName) {
      const parts = r.condition?.split('=') || [];
      for (const part of parts) {
        const trimmed = part.trim();
        const dotIdx = trimmed.lastIndexOf('.');
        if (dotIdx > -1) {
          const tbl = trimmed.slice(0, dotIdx);
          const col = trimmed.slice(dotIdx + 1);
          if (tbl === modelName) {
            fkCols.push(col);
          }
        }
      }
    }
  }
  return fkCols;
}

export default function ModelingPage() {
  const { markNeedsRedeploy } = useConnection();
  const [models, setModels] = useState<Model[]>([]);
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [selectedModel, setSelectedModel] = useState<Model | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Editing state
  const [editing, setEditing] = useState(false);
  const [editDesc, setEditDesc] = useState('');
  const [editColDescs, setEditColDescs] = useState<Record<string, string>>({});
  const [editColDisplayNames, setEditColDisplayNames] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    loadModels();
  }, []);

  const loadModels = async () => {
    try {
      const res = await api.getModels();
      setModels(res.models || []);
      setRelationships(res.relationships || []);
      buildDiagram(res.models || [], res.relationships || []);
    } catch {
      message.warning('Could not load models. Is the server running?');
    }
  };

  const openDrawer = useCallback((model: Model) => {
    setSelectedModel(model);
    setEditing(false);
    setDrawerOpen(true);
  }, []);

  const startEditing = () => {
    if (!selectedModel) return;
    setEditDesc(selectedModel.description || '');
    const colDescs: Record<string, string> = {};
    const colNames: Record<string, string> = {};
    for (const c of selectedModel.columns) {
      colDescs[c.name] = c.description || '';
      colNames[c.name] = c.display_name || '';
    }
    setEditColDescs(colDescs);
    setEditColDisplayNames(colNames);
    setEditing(true);
  };

  const cancelEditing = () => {
    setEditing(false);
  };

  const saveMetadata = async () => {
    if (!selectedModel) return;
    setSaving(true);
    try {
      const columnsData = selectedModel.columns.map(c => ({
        name: c.name,
        description: editColDescs[c.name] ?? c.description,
        display_name: editColDisplayNames[c.name] ?? c.display_name,
      }));
      await api.updateModel(selectedModel.name, {
        description: editDesc,
        columns: columnsData,
      });
      message.success('Metadata updated');
      setEditing(false);
      markNeedsRedeploy();
      loadModels();
    } catch (err: any) {
      message.error(err.message || 'Failed to save metadata');
    }
    setSaving(false);
  };

  const buildDiagram = (mdls: Model[], rels: Relationship[]) => {
    const cols = 3;
    const gapX = 380;
    const gapY = 400;
    const newNodes = mdls.map((m, i) => ({
      id: m.name,
      type: 'modelNode',
      position: { x: (i % cols) * gapX + 40, y: Math.floor(i / cols) * gapY + 40 },
      data: {
        model: m,
        fkColumns: extractFkColumns(rels, m.name),
        onNodeClick: (model: Model) => {
          setSelectedModel(model);
          setEditing(false);
          setDrawerOpen(true);
        },
      },
    }));

    const newEdges = rels.map((r, i) => ({
      id: `e-${i}`,
      source: r.model_from,
      target: r.model_to,
      type: 'smoothstep',
      style: { stroke: '#0D0D0D', strokeWidth: 2 },
      animated: false,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: '#0D0D0D',
        width: 16,
        height: 16,
      },
      label: r.join_type,
      labelStyle: { fontSize: 9, fill: '#0D0D0D', fontFamily: 'Space Grotesk, sans-serif', fontWeight: 700 },
      labelBgStyle: { fill: '#FFE600', fillOpacity: 1, stroke: '#0D0D0D', strokeWidth: 1 },
      labelBgPadding: [4, 2] as [number, number],
      labelBgBorderRadius: 0,
    }));

    setNodes(newNodes);
    setEdges(newEdges);
  };

  /* ── Column table columns (with inline editing) ── */
  const colTableCols = [
    {
      title: 'Name', dataIndex: 'name', key: 'name', width: 160,
      render: (name: string) => {
        const isPk = name === selectedModel?.primary_key;
        const isFk = selectedModel
          ? extractFkColumns(relationships, selectedModel.name).includes(name)
          : false;
        return (
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {isPk && <Tag color="gold" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>PK</Tag>}
            {isFk && !isPk && <Tag color="geekblue" style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>FK</Tag>}
            <span style={{ fontWeight: isPk ? 600 : 400 }}>{name}</span>
          </span>
        );
      },
    },
    {
      title: 'Alias', dataIndex: 'display_name', key: 'display_name', width: 140,
      render: (val: string, record: any) => {
        if (editing) {
          return (
            <Input
              size="small"
              value={editColDisplayNames[record.name] ?? val}
              onChange={e => setEditColDisplayNames(prev => ({ ...prev, [record.name]: e.target.value }))}
              placeholder="Display name"
              style={{ fontSize: 12 }}
            />
          );
        }
        return val || <Text type="secondary">-</Text>;
      },
    },
    { title: 'Type', dataIndex: 'type', key: 'type', width: 100,
      render: (t: string) => <Text code style={{ fontSize: 12 }}>{t}</Text>,
    },
    {
      title: 'Description', dataIndex: 'description', key: 'description',
      render: (d: string, record: any) => {
        if (editing) {
          return (
            <Input
              size="small"
              value={editColDescs[record.name] ?? d}
              onChange={e => setEditColDescs(prev => ({ ...prev, [record.name]: e.target.value }))}
              placeholder="Column description"
              style={{ fontSize: 12 }}
            />
          );
        }
        return <span style={{ color: '#8c8c8c' }}>{d || '-'}</span>;
      },
    },
  ];

  const sidebar = (
    <SidebarSection>
      <SidebarLabel>Models ({models.length})</SidebarLabel>
      {models.map(m => (
        <ModelItem
          key={m.name}
          $active={selectedModel?.name === m.name}
          onClick={() => openDrawer(m)}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#8c8c8c" strokeWidth="2">
            <ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
          </svg>
          {m.name}
        </ModelItem>
      ))}
    </SidebarSection>
  );

  return (
    <RequireConnection>
      <Head><title>Modeling — askDataAI</title></Head>
      <SiderLayout sidebar={sidebar}>
        <div style={{ width: '100%', height: '100%' }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            fitView
            maxZoom={1.5}
            minZoom={0.3}
            proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{
              type: 'smoothstep',
            }}
          >
            <MiniMap
              style={{
                height: 100,
                border: '2px solid #0D0D0D',
                boxShadow: '3px 3px 0 #0D0D0D',
                background: '#F7F6F2',
              }}
              maskColor="rgba(255,230,0,0.12)"
              zoomable
              pannable
            />
            <Controls
              showInteractive={false}
              style={{
                border: '2px solid #0D0D0D',
                boxShadow: '3px 3px 0 #0D0D0D',
                borderRadius: 0,
              }}
            />
            <Background
              gap={28}
              size={1.5}
              color="#0D0D0D"
              style={{ opacity: 0.08 }}
            />
          </ReactFlow>
        </div>

        <Drawer
          open={drawerOpen}
          onClose={() => { setDrawerOpen(false); setEditing(false); }}
          title={selectedModel?.name || ''}
          width={760}
          destroyOnClose
          extra={
            editing ? (
              <div style={{ display: 'flex', gap: 8 }}>
                <Button icon={<CloseOutlined />} onClick={cancelEditing}>Cancel</Button>
                <Button type="primary" icon={<SaveOutlined />} onClick={saveMetadata} loading={saving}>Save</Button>
              </div>
            ) : (
              <Button icon={<EditOutlined />} onClick={startEditing}>Edit Metadata</Button>
            )
          }
        >
          {selectedModel && (
            <>
              <MetaRow>
                <MetaField>
                  <MetaLabel>Table Reference</MetaLabel>
                  <MetaValue>{selectedModel.table_reference || selectedModel.name}</MetaValue>
                </MetaField>
                <MetaField>
                  <MetaLabel>Primary Key</MetaLabel>
                  <MetaValue>
                    <Tag color="gold">{selectedModel.primary_key || 'None'}</Tag>
                  </MetaValue>
                </MetaField>
              </MetaRow>

              <MetaField style={{ marginBottom: 24 }}>
                <MetaLabel>Description</MetaLabel>
                {editing ? (
                  <TextArea
                    value={editDesc}
                    onChange={e => setEditDesc(e.target.value)}
                    rows={3}
                    placeholder="Describe this model/table..."
                    style={{ fontSize: 13 }}
                  />
                ) : (
                  <MetaValue>{selectedModel.description || '-'}</MetaValue>
                )}
              </MetaField>

              <MetaField style={{ marginBottom: 24 }}>
                <MetaLabel>Columns ({selectedModel.columns.length})</MetaLabel>
                <Table
                  dataSource={selectedModel.columns.map((c, i) => ({ ...c, key: i }))}
                  columns={colTableCols}
                  size="small"
                  pagination={false}
                  style={{ marginTop: 8 }}
                />
              </MetaField>

              <MetaField>
                <MetaLabel>Relationships</MetaLabel>
                {relationships
                  .filter(r => r.model_from === selectedModel.name || r.model_to === selectedModel.name)
                  .map((r, i) => (
                    <div key={i} style={{ padding: '8px 0', fontSize: 13, color: '#434343', borderBottom: '1px solid #f0f0f0' }}>
                      <div>
                        <Text strong>{r.model_from}</Text>
                        <Text type="secondary"> → </Text>
                        <Text strong>{r.model_to}</Text>
                        <Tag color="blue" style={{ marginLeft: 8, fontSize: 11 }}>{r.join_type}</Tag>
                      </div>
                      {r.condition && (
                        <div style={{ marginTop: 4 }}>
                          <code style={{ fontSize: 12, color: '#8c8c8c', background: '#f5f5f5', padding: '2px 6px', borderRadius: 3 }}>
                            {r.condition}
                          </code>
                        </div>
                      )}
                    </div>
                  ))
                }
                {relationships.filter(r => r.model_from === selectedModel.name || r.model_to === selectedModel.name).length === 0 && (
                  <Text type="secondary">No relationships</Text>
                )}
              </MetaField>
            </>
          )}
        </Drawer>
      </SiderLayout>
    </RequireConnection>
  );
}
