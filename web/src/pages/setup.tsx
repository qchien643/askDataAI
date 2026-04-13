import { useState } from 'react';
import { useRouter } from 'next/router';
import Head from 'next/head';
import styled from 'styled-components';
import { Button, Input, message } from 'antd';
import { api } from '@/hooks/useApi';
import { useConnection } from '@/contexts/ConnectionContext';

const Page = styled.div`
  min-height: 100vh;
  background: var(--m-bg);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  position: relative;
  overflow: hidden;

  /* Memphis multi-dot background */
  &::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
      radial-gradient(circle, rgba(255,51,102,0.08) 1.5px, transparent 1.5px),
      radial-gradient(circle, rgba(0,212,255,0.06) 1.5px, transparent 1.5px);
    background-size:   28px 28px, 28px 28px;
    background-position: 0 0, 14px 14px;
    pointer-events: none;
  }

  /* Memphis top color bar */
  &::after {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 6px;
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
  }
`;

const LogoArea = styled.div`
  text-align: center;
  margin-bottom: 32px;
`;

const LogoIcon = styled.div`
  width: 52px;
  height: 52px;
  background: var(--m-yellow);
  border: 3px solid var(--m-black);
  box-shadow: 5px 5px 0 var(--m-black);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--m-black);
  font-weight: 900;
  font-size: 24px;
  margin: 0 auto 14px;
  font-family: 'Space Grotesk', sans-serif;
`;

const Title = styled.h1`
  font-size: 26px;
  font-weight: 900;
  font-family: 'Space Grotesk', sans-serif;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--m-black);
  margin-bottom: 8px;
`;

const Subtitle = styled.p`
  font-size: 12px;
  font-weight: 600;
  font-family: 'Space Grotesk', sans-serif;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

const Steps = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  margin-bottom: 32px;
`;

const StepCircle = styled.div<{ $active: boolean }>`
  width: 26px;
  height: 26px;
  background: ${p => p.$active ? 'var(--m-yellow)' : 'rgba(0,0,0,0.06)'};
  color: ${p => p.$active ? 'var(--m-black)' : '#aaa'};
  border: 2px solid ${p => p.$active ? 'var(--m-black)' : '#ccc'};
  box-shadow: ${p => p.$active ? '2px 2px 0 var(--m-black)' : 'none'};
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 800;
  font-family: 'Space Grotesk', sans-serif;
`;

const StepLine = styled.div`
  width: 60px;
  height: 3px;
  background: linear-gradient(90deg, rgba(13,13,13,0.1), rgba(13,13,13,0.05));
  margin: 0 6px;
`;

const StepLabel = styled.span<{ $active: boolean }>`
  font-size: 11px;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: ${p => p.$active ? 800 : 500};
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: ${p => p.$active ? 'var(--m-black)' : '#aaa'};
  margin-left: 6px;
`;

const Card = styled.div`
  width: 100%;
  max-width: 560px;
  background: white;
  border: 2.5px solid var(--m-black);
  box-shadow: 6px 6px 0 var(--m-black);
  padding: 32px;
  position: relative;
  overflow: hidden;
  z-index: 1;

  /* Memphis colored top stripe */
  &::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, var(--m-yellow), var(--m-pink), var(--m-cyan));
    pointer-events: none;
  }
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
        <title>Setup — askDataAI</title>
      </Head>
      <Page>
        <LogoArea>
          <LogoIcon>A</LogoIcon>
          <Title>askDataAI</Title>
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
