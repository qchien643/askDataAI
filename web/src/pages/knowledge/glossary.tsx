import { useState, useEffect } from 'react';
import Head from 'next/head';
import styled from 'styled-components';
import { Button, Table, Modal, Input, Tag, message, Typography, Spin } from 'antd';
import { BookOutlined } from '@ant-design/icons';
import SiderLayout from '@/components/layouts/SiderLayout';
import KnowledgeSidebar from '@/components/sidebar/KnowledgeSidebar';
import RequireConnection from '@/components/guards/RequireConnection';
import { useConnection } from '@/contexts/ConnectionContext';
import { api } from '@/hooks/useApi';

const { Text } = Typography;

const PageHeader = styled.div`
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 24px;
`;
const PageTitle = styled.h1`
  font-size: 20px; font-weight: 600; color: #262626;
  display: flex; align-items: center; gap: 8px;
`;
const PageDesc = styled.p`
  font-size: 14px; color: #8c8c8c; margin-top: 8px; max-width: 600px;
`;
const FormGroup = styled.div`margin-bottom: 16px;`;
const Label = styled.label`
  display: block; font-size: 13px; color: #434343; margin-bottom: 6px; font-weight: 500;
`;

interface GlossaryTerm {
  id: string;
  term: string;
  aliases: string[];
  sql_expression: string;
  description: string;
}

export default function GlossaryPage() {
  const { markNeedsRedeploy } = useConnection();
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ term: '', aliases: '', sql_expression: '', description: '' });

  useEffect(() => { loadTerms(); }, []);

  const loadTerms = async () => {
    setLoading(true);
    try {
      const res = await api.getGlossary();
      setTerms(res.terms || []);
    } catch (err: any) {
      message.error(err.message || 'Failed to load glossary');
    }
    setLoading(false);
  };

  const openAdd = () => {
    setEditId(null);
    setForm({ term: '', aliases: '', sql_expression: '', description: '' });
    setModalOpen(true);
  };

  const openEdit = (t: GlossaryTerm) => {
    setEditId(t.id);
    setForm({
      term: t.term,
      aliases: (t.aliases || []).join(', '),
      sql_expression: t.sql_expression || '',
      description: t.description || '',
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.term.trim()) { message.warning('Term is required'); return; }
    const aliases = form.aliases.split(',').map(a => a.trim()).filter(Boolean);
    const data = { term: form.term, aliases, sql_expression: form.sql_expression, description: form.description };

    setSaving(true);
    try {
      if (editId) {
        await api.updateGlossaryTerm(editId, data);
        message.success('Updated — nhấn Deploy để áp dụng');
      } else {
        await api.addGlossaryTerm(data);
        message.success('Created — nhấn Deploy để áp dụng');
      }
      setModalOpen(false);
      markNeedsRedeploy();
      loadTerms();
    } catch (err: any) {
      message.error(err.message || 'Failed to save');
    }
    setSaving(false);
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteGlossaryTerm(id);
      message.success('Deleted — nhấn Deploy để áp dụng');
      markNeedsRedeploy();
      loadTerms();
    } catch (err: any) {
      message.error(err.message || 'Failed to delete');
    }
  };

  const columns = [
    { title: 'Term', dataIndex: 'term', width: 140, render: (t: string) => <Text strong>{t}</Text> },
    {
      title: 'Aliases', dataIndex: 'aliases', width: 220,
      render: (a: string[]) => (
        <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 4 }}>
          {(a || []).map(alias => <Tag key={alias} style={{ margin: 0, borderRadius: 4 }}>{alias}</Tag>)}
        </div>
      ),
    },
    {
      title: 'SQL Expression', dataIndex: 'sql_expression', width: 240,
      render: (s: string) => s ? <code style={{ fontSize: 12, color: '#434343', background: '#f5f5f5', padding: '2px 6px', borderRadius: 3 }}>{s}</code> : <Text type="secondary">-</Text>,
    },
    {
      title: 'Description', dataIndex: 'description',
      render: (d: string) => <Text type="secondary">{d || '-'}</Text>,
    },
    {
      key: 'action', width: 80, align: 'center' as const,
      render: (_: any, record: GlossaryTerm) => (
        <div style={{ display: 'flex', gap: 4 }}>
          <Button size="small" type="text" onClick={() => openEdit(record)}>Edit</Button>
          <Button size="small" type="text" danger onClick={() => handleDelete(record.id)}>Del</Button>
        </div>
      ),
    },
  ];

  return (
    <RequireConnection>
      <Head><title>Business Glossary — Mini Wren AI</title></Head>
      <SiderLayout sidebar={<KnowledgeSidebar />}>
        <div style={{ padding: '24px 32px' }}>
          <PageHeader>
            <div>
              <PageTitle>
                <BookOutlined style={{ color: '#65676c' }} />
                Manage business glossary
              </PageTitle>
              <PageDesc>
                Define business terms and their SQL mappings.
                These help Mini Wren AI understand your domain-specific language.
              </PageDesc>
            </div>
            <Button type="primary" onClick={openAdd}>Add term</Button>
          </PageHeader>

          <Spin spinning={loading}>
            <Table
              dataSource={terms}
              columns={columns}
              rowKey="id"
              pagination={{ hideOnSinglePage: true, pageSize: 10, size: 'small' }}
              scroll={{ x: 900 }}
            />
          </Spin>

          <Modal
            open={modalOpen}
            onCancel={() => setModalOpen(false)}
            onOk={handleSave}
            confirmLoading={saving}
            title={editId ? 'Edit term' : 'Add term'}
            okText="Save"
            width={560}
          >
            <FormGroup>
              <Label>Term</Label>
              <Input value={form.term} onChange={e => setForm(p => ({ ...p, term: e.target.value }))} placeholder="e.g. doanh thu" />
            </FormGroup>
            <FormGroup>
              <Label>Aliases (comma-separated)</Label>
              <Input value={form.aliases} onChange={e => setForm(p => ({ ...p, aliases: e.target.value }))} placeholder="revenue, sales" />
            </FormGroup>
            <FormGroup>
              <Label>SQL Expression</Label>
              <Input value={form.sql_expression} onChange={e => setForm(p => ({ ...p, sql_expression: e.target.value }))} placeholder="SUM(SalesAmount)" style={{ fontFamily: "'JetBrains Mono', monospace" }} />
            </FormGroup>
            <FormGroup>
              <Label>Description</Label>
              <Input value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} placeholder="Mô tả thuật ngữ" />
            </FormGroup>
          </Modal>
        </div>
      </SiderLayout>
    </RequireConnection>
  );
}
