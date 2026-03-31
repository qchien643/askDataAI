import { useState, useEffect } from 'react';
import Head from 'next/head';
import styled from 'styled-components';
import { Switch, Slider, Button, message, Spin } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useRouter } from 'next/router';
import SiderLayout from '@/components/layouts/SiderLayout';
import RequireConnection from '@/components/guards/RequireConnection';
import { useConnection } from '@/contexts/ConnectionContext';
import { api } from '@/hooks/useApi';

/* ── Sidebar ── */
const SidebarSection = styled.div`padding: 12px 0;`;
const SidebarLabel = styled.div`
  font-size: 12px; font-weight: 700; color: #434343;
  padding: 5px 16px;
`;
const MenuItem = styled.button<{ $active?: boolean }>`
  width: 100%; display: block; text-align: left;
  padding: 6px 16px; border: none; cursor: pointer;
  background: ${p => p.$active ? '#d9d9d9' : 'transparent'};
  color: #65676c; font-size: 13px; font-family: inherit;
  &:hover { background: ${p => p.$active ? '#d9d9d9' : '#f0f0f0'}; }
`;

/* ── Content ── */
const PageTitle = styled.h1`
  font-size: 20px; font-weight: 600; color: #262626; margin-bottom: 24px;
`;
const Section = styled.div`margin-bottom: 32px;`;
const SectionTitle = styled.h3`
  font-size: 14px; font-weight: 700; color: #434343; margin-bottom: 4px;
`;
const SectionDesc = styled.p`
  font-size: 13px; color: #8c8c8c; margin-bottom: 16px;
`;
const Divider = styled.hr`
  border: none; border-top: 1px solid #f0f0f0; margin: 24px 0;
`;
const InfoRow = styled.div`
  display: flex; padding: 8px 0; font-size: 14px;
`;
const InfoLabel = styled.div`
  width: 140px; color: #8c8c8c; flex-shrink: 0;
`;
const InfoValue = styled.div`color: #262626;`;
const StatusBadge = styled.span<{ $ok: boolean }>`
  display: inline-flex; align-items: center; gap: 6px;
  color: ${p => p.$ok ? '#52c41a' : '#ff4d4f'};
`;

const FeatureRow = styled.div`
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 0; border-bottom: 1px solid #f5f5f5;
`;
const FeatureInfo = styled.div``;
const FeatureName = styled.div`font-size: 14px; color: #262626;`;
const FeatureDesc = styled.div`font-size: 12px; color: #8c8c8c; margin-top: 2px;`;

const SliderRow = styled.div`
  display: flex; align-items: center; gap: 16px; margin-bottom: 16px;
`;
const SliderLabel = styled.div`
  width: 120px; font-size: 14px; color: #262626; flex-shrink: 0;
`;

export default function SettingsPage() {
  const router = useRouter();
  const { info, refresh } = useConnection();
  const [loading, setLoading] = useState(true);
  const [features, setFeatures] = useState<Record<string, boolean>>({});
  const [generation, setGeneration] = useState<Record<string, number>>({});

  useEffect(() => { loadSettings(); }, []);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const settings = await api.getSettings();
      setFeatures(settings.features || {});
      setGeneration(settings.generation || {});
    } catch (err: any) {
      message.error(err.message || 'Failed to load settings');
    }
    setLoading(false);
  };

  const toggleFeature = async (key: string) => {
    const updated = { ...features, [key]: !features[key] };
    setFeatures(updated);
    try {
      await api.updateSettings({ features: { [key]: updated[key] } });
    } catch (err: any) {
      message.error('Failed to save');
      setFeatures(features); // rollback
    }
  };

  const saveGeneration = async (key: string, value: number) => {
    const updated = { ...generation, [key]: value };
    setGeneration(updated);
    try {
      await api.updateSettings({ generation: { [key]: value } });
    } catch {
      setGeneration(generation);
    }
  };

  const handleDisconnect = async () => {
    try {
      await api.disconnect();
      message.success('Disconnected — ChromaDB index cleared');
      refresh();
      router.push('/setup');
    } catch (err: any) {
      message.error(err.message || 'Disconnect failed');
    }
  };

  const featureList = [
    { key: 'enable_schema_linking', name: 'Schema Linking', desc: 'Identify relevant tables and columns' },
    { key: 'enable_column_pruning', name: 'Column Pruning', desc: 'Remove irrelevant columns from context' },
    { key: 'enable_cot_reasoning', name: 'Chain-of-Thought', desc: 'Generate reasoning steps before SQL' },
    { key: 'enable_voting', name: 'Voting', desc: 'Generate multiple candidates and vote' },
    { key: 'enable_glossary', name: 'Glossary', desc: 'Use business glossary for term mapping' },
    { key: 'enable_memory', name: 'Query History', desc: 'Learn from past successful queries' },
  ];

  const sidebar = (
    <SidebarSection>
      <SidebarLabel>Settings</SidebarLabel>
      <MenuItem $active={true}>Data Source</MenuItem>
      <MenuItem>Pipeline</MenuItem>
      <MenuItem>About</MenuItem>
    </SidebarSection>
  );

  return (
    <RequireConnection>
      <Head><title>Settings — Mini Wren AI</title></Head>
      <SiderLayout sidebar={sidebar}>
        <Spin spinning={loading}>
          <div style={{ padding: '24px 32px', maxWidth: 720 }}>
            <PageTitle>
              <SettingOutlined style={{ marginRight: 8, color: '#65676c' }} />
              Data Source Settings
            </PageTitle>

            <Section>
              <SectionTitle>Connection</SectionTitle>
              <InfoRow>
                <InfoLabel>Data Source</InfoLabel>
                <InfoValue>SQL Server</InfoValue>
              </InfoRow>
              <InfoRow>
                <InfoLabel>Host</InfoLabel>
                <InfoValue>{info.host || '-'}</InfoValue>
              </InfoRow>
              <InfoRow>
                <InfoLabel>Port</InfoLabel>
                <InfoValue>{info.port || '-'}</InfoValue>
              </InfoRow>
              <InfoRow>
                <InfoLabel>Database</InfoLabel>
                <InfoValue>{info.database || '-'}</InfoValue>
              </InfoRow>
              <InfoRow>
                <InfoLabel>Models</InfoLabel>
                <InfoValue>{info.models_count || 0}</InfoValue>
              </InfoRow>
              <InfoRow>
                <InfoLabel>Status</InfoLabel>
                <InfoValue>
                  <StatusBadge $ok={info.connected}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: info.connected ? '#52c41a' : '#ff4d4f', display: 'inline-block' }} />
                    {info.connected ? 'Connected' : 'Disconnected'}
                  </StatusBadge>
                </InfoValue>
              </InfoRow>
              <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                <Button onClick={() => refresh()}>Refresh</Button>
                {info.connected && (
                  <Button type="link" danger onClick={handleDisconnect}>Disconnect</Button>
                )}
              </div>
            </Section>

            <Divider />

            <Section>
              <SectionTitle>Pipeline Features</SectionTitle>
              <SectionDesc>Toggle features for the Text-to-SQL pipeline</SectionDesc>
              {featureList.map(f => (
                <FeatureRow key={f.key}>
                  <FeatureInfo>
                    <FeatureName>
                      {f.name}
                      {f.key === 'enable_voting' && (
                        <span style={{ fontSize: 11, color: '#8c8c8c', marginLeft: 6 }}>(disabled)</span>
                      )}
                    </FeatureName>
                    <FeatureDesc>{f.desc}</FeatureDesc>
                  </FeatureInfo>
                  <Switch
                    checked={f.key === 'enable_voting' ? false : (features[f.key] ?? false)}
                    onChange={() => toggleFeature(f.key)}
                    disabled={f.key === 'enable_voting'}
                  />
                </FeatureRow>
              ))}
            </Section>

            <Divider />

            <Section>
              <SectionTitle>Generation Parameters</SectionTitle>
              <SliderRow>
                <SliderLabel>Candidates</SliderLabel>
                <Slider
                  min={1} max={5} value={generation.num_candidates ?? 3}
                  onChangeComplete={v => saveGeneration('num_candidates', v)}
                  style={{ flex: 1 }}
                />
                <span style={{ width: 24, textAlign: 'center', color: '#262626' }}>{generation.num_candidates ?? 3}</span>
              </SliderRow>
              <SliderRow>
                <SliderLabel>Temperature</SliderLabel>
                <Slider
                  min={0} max={1} step={0.1} value={generation.temperature ?? 0.1}
                  onChangeComplete={v => saveGeneration('temperature', v)}
                  style={{ flex: 1 }}
                />
                <span style={{ width: 24, textAlign: 'center', color: '#262626' }}>{generation.temperature ?? 0.1}</span>
              </SliderRow>
            </Section>
          </div>
        </Spin>
      </SiderLayout>
    </RequireConnection>
  );
}
