import { useState, useEffect } from 'react';
import Head from 'next/head';
import styled from 'styled-components';
import { Button, Table, Modal, Input, message, Typography, Spin } from 'antd';
import { FunctionOutlined } from '@ant-design/icons';
import SiderLayout from '@/components/layouts/SiderLayout';
import KnowledgeSidebar from '@/components/sidebar/KnowledgeSidebar';
import RequireConnection from '@/components/guards/RequireConnection';
import { useConnection } from '@/contexts/ConnectionContext';
import { api } from '@/hooks/useApi';

const { Paragraph, Text } = Typography;
const { TextArea } = Input;

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
const SqlBlock = styled.pre`
  background: #1f1f1f; color: #e6e6e6; border-radius: 4px;
  padding: 8px 12px; font-size: 12px; line-height: 1.5;
  overflow-x: auto; max-height: 130px;
  font-family: 'JetBrains Mono', monospace;
  margin: 0;
`;
const FormGroup = styled.div`margin-bottom: 16px;`;
const Label = styled.label`
  display: block; font-size: 13px; color: #434343; margin-bottom: 6px; font-weight: 500;
`;

interface SQLPair {
  id: string;
  question: string;
  sql: string;
  created_at?: string;
}

export default function QuestionSQLPairsPage() {
  const { markNeedsRedeploy } = useConnection();
  const [pairs, setPairs] = useState<SQLPair[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ question: '', sql: '' });

  useEffect(() => { loadPairs(); }, []);

  const loadPairs = async () => {
    setLoading(true);
    try {
      const res = await api.getSqlPairs();
      setPairs(res.pairs || []);
    } catch (err: any) {
      message.error(err.message || 'Failed to load SQL pairs');
    }
    setLoading(false);
  };

  const openAdd = () => {
    setEditId(null);
    setForm({ question: '', sql: '' });
    setModalOpen(true);
  };

  const openEdit = (pair: SQLPair) => {
    setEditId(pair.id);
    setForm({ question: pair.question, sql: pair.sql });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.question.trim() || !form.sql.trim()) {
      message.warning('Please fill in both fields');
      return;
    }
    setSaving(true);
    try {
      if (editId) {
        await api.updateSqlPair(editId, form);
        message.success('Updated — nhấn Deploy để áp dụng');
      } else {
        await api.addSqlPair(form);
        message.success('Created — nhấn Deploy để áp dụng');
      }
      setModalOpen(false);
      markNeedsRedeploy();
      loadPairs();
    } catch (err: any) {
      message.error(err.message || 'Failed to save');
    }
    setSaving(false);
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteSqlPair(id);
      message.success('Deleted — nhấn Deploy để áp dụng');
      markNeedsRedeploy();
      loadPairs();
    } catch (err: any) {
      message.error(err.message || 'Failed to delete');
    }
  };

  const columns = [
    {
      title: 'Question', dataIndex: 'question', width: 250,
      render: (q: string) => <Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 0 }}>{q}</Paragraph>,
    },
    {
      title: 'SQL statement', dataIndex: 'sql', width: '50%',
      render: (sql: string) => <SqlBlock>{sql}</SqlBlock>,
    },
    {
      title: 'Created', dataIndex: 'created_at', width: 110,
      render: (d: string) => <Text type="secondary" style={{ fontSize: 13 }}>{d || '-'}</Text>,
    },
    {
      key: 'action', width: 80, align: 'center' as const,
      render: (_: any, record: SQLPair) => (
        <div style={{ display: 'flex', gap: 4 }}>
          <Button size="small" type="text" onClick={() => openEdit(record)}>Edit</Button>
          <Button size="small" type="text" danger onClick={() => handleDelete(record.id)}>Del</Button>
        </div>
      ),
    },
  ];

  return (
    <RequireConnection>
      <Head><title>Question-SQL Pairs — Mini Wren AI</title></Head>
      <SiderLayout sidebar={<KnowledgeSidebar />}>
        <div style={{ padding: '24px 32px' }}>
          <PageHeader>
            <div>
              <PageTitle>
                <FunctionOutlined style={{ color: '#65676c' }} />
                Manage question-SQL pairs
              </PageTitle>
              <PageDesc>
                Manage saved question-SQL pairs. These help Mini Wren AI learn
                how your organization writes SQL queries.
              </PageDesc>
            </div>
            <Button type="primary" onClick={openAdd}>Add question-SQL pair</Button>
          </PageHeader>

          <Spin spinning={loading}>
            <Table
              dataSource={pairs}
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
            title={editId ? 'Edit question-SQL pair' : 'Add question-SQL pair'}
            okText="Save"
            width={640}
          >
            <FormGroup>
              <Label>Question</Label>
              <Input
                value={form.question}
                onChange={e => setForm(prev => ({ ...prev, question: e.target.value }))}
                placeholder="Enter a natural language question"
              />
            </FormGroup>
            <FormGroup>
              <Label>SQL Statement</Label>
              <TextArea
                value={form.sql}
                onChange={e => setForm(prev => ({ ...prev, sql: e.target.value }))}
                placeholder="Enter the corresponding SQL"
                rows={6}
                style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13 }}
              />
            </FormGroup>
          </Modal>
        </div>
      </SiderLayout>
    </RequireConnection>
  );
}
