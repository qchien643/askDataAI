import { useState } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import styled from 'styled-components';
import { Button, Input, message } from 'antd';
import { api } from '@/hooks/useApi';
import { useConnection } from '@/contexts/ConnectionContext';

const Page = styled.div`
  min-height: 100vh;
  background: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
`;

const LogoArea = styled.div`
  text-align: center;
  margin-bottom: 32px;
`;

const LogoIcon = styled.div`
  width: 48px;
  height: 48px;
  background: #4B6BFB;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: 700;
  font-size: 20px;
  margin: 0 auto 12px;
`;

const Title = styled.h1`
  font-size: 28px;
  font-weight: 600;
  color: #262626;
  margin-bottom: 8px;
`;

const Subtitle = styled.p`
  font-size: 14px;
  color: #8c8c8c;
`;

const Steps = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  margin-bottom: 32px;
`;

const StepCircle = styled.div<{ $active: boolean }>`
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: ${p => p.$active ? '#4B6BFB' : '#d9d9d9'};
  color: ${p => p.$active ? 'white' : '#8c8c8c'};
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
`;

const StepLine = styled.div`
  width: 60px;
  height: 2px;
  background: #d9d9d9;
  margin: 0 8px;
`;

const StepLabel = styled.span<{ $active: boolean }>`
  font-size: 12px;
  color: ${p => p.$active ? '#262626' : '#8c8c8c'};
  margin-left: 6px;
  font-weight: ${p => p.$active ? 500 : 400};
`;

const Card = styled.div`
  width: 100%;
  max-width: 560px;
  background: white;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 32px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
`;

const CardTitle = styled.h2`
  font-size: 18px;
  font-weight: 600;
  color: #262626;
  margin-bottom: 4px;
`;

const CardDesc = styled.p`
  font-size: 14px;
  color: #8c8c8c;
  margin-bottom: 24px;
`;

const FormGroup = styled.div`
  margin-bottom: 16px;
`;

const Label = styled.label`
  display: block;
  font-size: 13px;
  color: #434343;
  margin-bottom: 6px;
  font-weight: 500;
`;

const SampleBanner = styled.div`
  background: #F0F5FF;
  border-radius: 4px;
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 20px 0;
`;

const SampleInfo = styled.div``;

const SampleTitle = styled.div`
  font-weight: 600;
  color: #262626;
  font-size: 14px;
`;

const SampleDesc = styled.div`
  font-size: 13px;
  color: #8c8c8c;
  margin-top: 2px;
`;

const ButtonRow = styled.div`
  display: flex;
  justify-content: space-between;
  margin-top: 24px;
`;

export default function SetupPage() {
  const router = useRouter();
  const { refresh } = useConnection();
  const [form, setForm] = useState({
    displayName: '',
    host: 'localhost',
    port: '1433',
    database: '',
    username: 'sa',
    password: '',
  });
  const [testing, setTesting] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const set = (key: string, val: string) =>
    setForm(prev => ({ ...prev, [key]: val }));

  const useSampleData = () => {
    setForm({
      displayName: 'AdventureWorksDW2025',
      host: 'localhost',
      port: '1433',
      database: 'AdventureWorksDW2025',
      username: 'sa',
      password: '1890Cccp%',
    });
    message.success('Sample data loaded');
  };

  const getConnectionData = () => ({
    host: form.host,
    port: parseInt(form.port) || 1433,
    database: form.database,
    username: form.username,
    password: form.password,
  });

  const testConnection = async () => {
    if (!form.database) {
      message.warning('Please enter a database name');
      return;
    }
    setTesting(true);
    try {
      const res = await api.testConnection(getConnectionData());
      if (res.status === 'connected') {
        message.success(`Connected to ${res.database_name} (v${res.server_version})`);
      } else {
        message.error(res.error || 'Connection failed');
      }
    } catch (err: any) {
      message.error(err.message || 'Connection failed — is the server running?');
    }
    setTesting(false);
  };

  const handleNext = async () => {
    if (!form.database) {
      message.warning('Please enter a database name');
      return;
    }
    setConnecting(true);
    try {
      const res = await api.connect(getConnectionData());
      if (res.success) {
        message.success(`Connected — ${res.models_count} models deployed`);
        await refresh(); // Update ConnectionContext immediately
        router.push('/home');
      } else {
        message.error(res.message || 'Connection failed');
      }
    } catch (err: any) {
      message.error(err.message || 'Failed to connect. Check server status.');
    }
    setConnecting(false);
  };

  return (
    <>
      <Head>
        <title>Setup — Mini Wren AI</title>
      </Head>
      <Page>
        <LogoArea>
          <LogoIcon>W</LogoIcon>
          <Title>Mini Wren AI</Title>
          <Subtitle>Connect your data source to get started</Subtitle>
        </LogoArea>

        <Steps>
          <StepCircle $active={true}>1</StepCircle>
          <StepLabel $active={true}>Connect</StepLabel>
          <StepLine />
          <StepCircle $active={false}>2</StepCircle>
          <StepLabel $active={false}>Select Tables</StepLabel>
          <StepLine />
          <StepCircle $active={false}>3</StepCircle>
          <StepLabel $active={false}>Relationships</StepLabel>
        </Steps>

        <Card>
          <CardTitle>Connect to SQL Server</CardTitle>
          <CardDesc>Enter connection details for your database</CardDesc>

          <FormGroup>
            <Label>Display Name</Label>
            <Input
              value={form.displayName}
              onChange={e => set('displayName', e.target.value)}
              placeholder="My Database"
              size="large"
            />
          </FormGroup>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <FormGroup>
              <Label>Host</Label>
              <Input value={form.host} onChange={e => set('host', e.target.value)} size="large" />
            </FormGroup>
            <FormGroup>
              <Label>Port</Label>
              <Input value={form.port} onChange={e => set('port', e.target.value)} size="large" />
            </FormGroup>
          </div>
          <FormGroup>
            <Label>Database</Label>
            <Input
              value={form.database}
              onChange={e => set('database', e.target.value)}
              placeholder="Database name"
              size="large"
            />
          </FormGroup>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <FormGroup>
              <Label>Username</Label>
              <Input value={form.username} onChange={e => set('username', e.target.value)} size="large" />
            </FormGroup>
            <FormGroup>
              <Label>Password</Label>
              <Input.Password
                value={form.password}
                onChange={e => set('password', e.target.value)}
                placeholder="Enter password"
                size="large"
              />
            </FormGroup>
          </div>

          <SampleBanner>
            <SampleInfo>
              <SampleTitle>AdventureWorksDW2025</SampleTitle>
              <SampleDesc>Pre-configured sample database for testing</SampleDesc>
            </SampleInfo>
            <Button onClick={useSampleData}>Use Sample Data</Button>
          </SampleBanner>

          <ButtonRow>
            <Button onClick={testConnection} loading={testing}>
              Test Connection
            </Button>
            <Button type="primary" onClick={handleNext} loading={connecting}>
              Next
            </Button>
          </ButtonRow>
        </Card>
      </Page>
    </>
  );
}
