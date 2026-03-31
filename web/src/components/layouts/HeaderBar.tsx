import { useRouter } from 'next/router';
import styled from 'styled-components';
import { useConnection } from '@/contexts/ConnectionContext';
import { api } from '@/hooks/useApi';
import { message } from 'antd';
import { useState } from 'react';

const Header = styled.header`
  height: 48px;
  background: #262626;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 1px solid #434343;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
`;

const LogoArea = styled.div`
  display: flex;
  align-items: center;
  gap: 48px;
`;

const Logo = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  color: white;
  font-size: 14px;
  font-weight: 600;

  .logo-icon {
    width: 24px;
    height: 24px;
    background: #4B6BFB;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
  }
`;

const NavGroup = styled.div`
  display: flex;
  gap: 8px;
`;

const NavButton = styled.button<{ $active: boolean }>`
  background: ${p => p.$active ? 'rgba(255,255,255,0.20)' : 'transparent'};
  font-weight: ${p => p.$active ? '700' : '400'};
  color: white;
  border: none;
  border-radius: 14px;
  padding: 4px 16px;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s;

  &:hover {
    background: ${p => p.$active ? 'rgba(255,255,255,0.20)' : 'rgba(255,255,255,0.08)'};
  }
`;

const RightArea = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
`;

/* ── Connection badge ── */
const ConnectionBadge = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 14px;
  padding: 3px 12px;
  cursor: pointer;
  transition: background 0.15s;

  &:hover {
    background: rgba(255,255,255,0.14);
  }
`;

const StatusDot = styled.span<{ $color: string }>`
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${p => p.$color};
  display: inline-block;
  flex-shrink: 0;
`;

const BadgeText = styled.span`
  color: rgba(255,255,255,0.85);
  font-size: 12px;
  font-family: inherit;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

/* ── Deploy area ── */
const DeployArea = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const DeployButton = styled.button`
  background: #4B6BFB;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 4px 16px;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  font-weight: 500;
  transition: opacity 0.15s;

  &:hover {
    opacity: 0.9;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`;

const UndeployedLabel = styled.span`
  color: #faad14;
  font-size: 12px;
  font-weight: 500;
`;

export default function HeaderBar() {
  const router = useRouter();
  const path = router.pathname;
  const { info, needsRedeploy, refresh, clearNeedsRedeploy } = useConnection();
  const [deploying, setDeploying] = useState(false);

  const navItems = [
    { label: 'Home', path: '/home' },
    { label: 'Modeling', path: '/modeling' },
    { label: 'Knowledge', path: '/knowledge' },
    { label: 'Settings', path: '/settings' },
  ];

  const handleDeploy = async () => {
    setDeploying(true);
    try {
      const res = await api.deploy();
      if (res.success) {
        message.success('Deploy thành công — đã re-index');
        clearNeedsRedeploy();
        refresh();
      } else {
        message.error(res.message || 'Deploy thất bại');
      }
    } catch (err: any) {
      message.error(err.message || 'Deploy thất bại');
    }
    setDeploying(false);
  };

  return (
    <Header>
      <LogoArea>
        <Logo>
          <span className="logo-icon">W</span>
          Mini Wren AI
        </Logo>
        <NavGroup>
          {navItems.map(item => (
            <NavButton
              key={item.path}
              $active={path.startsWith(item.path)}
              onClick={() => router.push(
                item.path === '/knowledge' ? '/knowledge/question-sql-pairs' : item.path
              )}
            >
              {item.label}
            </NavButton>
          ))}
        </NavGroup>
      </LogoArea>

      <RightArea>
        {/* Deploy button — visible when needsRedeploy and connected */}
        {info.connected && needsRedeploy && (
          <DeployArea>
            <StatusDot $color="#faad14" />
            <UndeployedLabel>Có thay đổi chưa deploy</UndeployedLabel>
            <DeployButton onClick={handleDeploy} disabled={deploying}>
              {deploying ? 'Deploying...' : 'Deploy'}
            </DeployButton>
          </DeployArea>
        )}

        {/* Connection status badge */}
        <ConnectionBadge onClick={() => router.push('/settings')}>
          <StatusDot $color={info.connected ? '#52c41a' : '#ff4d4f'} />
          <BadgeText>
            {info.connected ? info.database || 'Connected' : 'Disconnected'}
          </BadgeText>
        </ConnectionBadge>
      </RightArea>
    </Header>
  );
}
