import { ReactNode } from 'react';
import { Spin } from 'antd';
import styled from 'styled-components';
import { useConnection } from '@/contexts/ConnectionContext';

const FullPageLoader = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: #fff;
`;

interface Props {
  children: ReactNode;
}

/**
 * Route guard — renders children only when connected.
 * Shows a full-page spinner while checking connection status.
 * Redirect to /setup is handled by ConnectionProvider.
 */
export default function RequireConnection({ children }: Props) {
  const { info, isLoading } = useConnection();

  if (isLoading) {
    return (
      <FullPageLoader>
        <Spin size="large" tip="Checking connection..." />
      </FullPageLoader>
    );
  }

  if (!info.connected) {
    // ConnectionProvider will redirect to /setup
    return (
      <FullPageLoader>
        <Spin size="large" tip="Redirecting to setup..." />
      </FullPageLoader>
    );
  }

  return <>{children}</>;
}
