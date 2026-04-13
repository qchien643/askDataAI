import { useRouter } from 'next/router';
import styled, { keyframes } from 'styled-components';
import { useConnection } from '@/contexts/ConnectionContext';
import { api } from '@/hooks/useApi';
import { message } from 'antd';
import { useState } from 'react';

/* ── Animations ── */
const floatY = keyframes`
  0%, 100% { transform: translateY(0px); }
  50%       { transform: translateY(-3px); }
`;

/* ══════════════════════════════════════
   HEADER — fixed top, full width
   • Left logo section = exact sidebar width (260px)
   •  This creates seamless corner where
     header-bottom meets sidebar-right
   ══════════════════════════════════════ */
const Header = styled.header`
  height: var(--header-h, 56px);
  background: var(--m-black);
  display: flex;
  align-items: stretch;     /* children fill full height */
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 300;
  /* Single bottom border — matched by sidebar border-right */
  border-bottom: 3px solid var(--m-black);
`;

/* ── Logo section — exactly 260px = sidebar width ── */
const LogoSection = styled.div`
  width: var(--sidebar-w, 260px);
  min-width: var(--sidebar-w, 260px);
  display: flex;
  align-items: center;
  padding: 0 16px;
  /* Right edge aligns with sidebar right border */
  border-right: 3px solid rgba(255,255,255,0.1);
  cursor: pointer;
  gap: 10px;
  flex-shrink: 0;
  transition: background 0.15s;

  &:hover { background: rgba(255,255,255,0.04); }
`;

const LogoBox = styled.div`
  width: 30px; height: 30px;
  background: var(--m-yellow);
  border: 2px solid rgba(255,255,255,0.2);
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 900;
  color: var(--m-black);
  font-family: 'Space Grotesk', sans-serif;
  animation: ${floatY} 3.5s ease-in-out infinite;
  flex-shrink: 0;
`;

const LogoText = styled.span`
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 800;
  font-size: 13px;
  color: white;
  text-transform: none;    /* preserve camelCase branding */
  letter-spacing: 0.5px;
  line-height: 1;

  span { color: var(--m-yellow); }       /* "Data" */
  .ai  { color: var(--m-pink); }         /* "AI" */
`;

/* ── Centre nav ── */
const NavSection = styled.nav`
  flex: 1;
  display: flex;
  align-items: center;
  padding: 0 24px;
  gap: 2px;
`;

const NavBtn = styled.button<{ $active: boolean }>`
  background: ${p => p.$active ? 'var(--m-yellow)' : 'transparent'};
  color: ${p => p.$active ? 'var(--m-black)' : 'rgba(255,255,255,0.60)'};
  border: none;
  border-bottom: ${p => p.$active ? '3px solid var(--m-pink)' : '3px solid transparent'};
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 800;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  padding: 0 18px;
  height: 100%;
  cursor: pointer;
  transition: background 0.1s, color 0.1s, border-color 0.1s;

  &:hover {
    background: ${p => p.$active ? 'var(--m-yellow)' : 'rgba(255,230,0,0.10)'};
    color: ${p => p.$active ? 'var(--m-black)' : 'white'};
  }
`;

/* ── Right area ── */
const RightSection = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border-left: 3px solid rgba(255,255,255,0.08);
`;

/* ── Connection badge ── */
const ConnBadge = styled.button<{ $on: boolean }>`
  display: flex;
  align-items: center;
  gap: 7px;
  background: ${p => p.$on ? 'rgba(0,230,118,0.12)' : 'rgba(255,23,68,0.14)'};
  border: 2px solid ${p => p.$on ? 'var(--m-green)' : 'var(--m-red)'};
  padding: 4px 14px;
  cursor: pointer;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 700;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: white;
  transition: transform 0.08s, box-shadow 0.08s;
  box-shadow: 2px 2px 0 ${p => p.$on ? 'var(--m-green)' : 'var(--m-red)'};

  &:hover {
    transform: translate(-1px, -1px);
    box-shadow: 3px 3px 0 ${p => p.$on ? 'var(--m-green)' : 'var(--m-red)'};
  }
`;

const Dot = styled.span<{ $on: boolean }>`
  width: 7px; height: 7px;
  border-radius: 50%;
  background: ${p => p.$on ? 'var(--m-green)' : 'var(--m-red)'};
  flex-shrink: 0;
  box-shadow: 0 0 5px ${p => p.$on ? 'var(--m-green)' : 'var(--m-red)'};
`;

/* ── Deploy area ── */
const DeployBtn = styled.button`
  background: var(--m-orange);
  color: var(--m-black);
  border: 2px solid var(--m-black);
  box-shadow: 3px 3px 0 rgba(0,0,0,0.5);
  padding: 4px 16px;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 800;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  cursor: pointer;
  transition: transform 0.08s, box-shadow 0.08s;

  &:hover { transform: translate(-1px,-1px); box-shadow: 4px 4px 0 rgba(0,0,0,0.5); }
  &:active { transform: translate(2px,2px); box-shadow: none; }
  &:disabled { opacity: 0.4; cursor: not-allowed; }
`;

const PendingTag = styled.span`
  color: var(--m-yellow);
  font-family: 'Space Grotesk', sans-serif;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.4px;
`;

/* ══════════════════════════════════════ */
export default function HeaderBar() {
  const router = useRouter();
  const path = router.pathname;
  const { info, needsRedeploy, refresh, clearNeedsRedeploy } = useConnection();
  const [deploying, setDeploying] = useState(false);

  const navItems = [
    { label: 'Home',      path: '/home' },
    { label: 'Modeling',  path: '/modeling' },
    { label: 'Knowledge', path: '/knowledge' },
    { label: 'Settings',  path: '/settings' },
  ];

  const handleDeploy = async () => {
    setDeploying(true);
    try {
      const res = await api.deploy();
      if (res.success) {
        message.success('Deploy thành công ✓');
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
      {/* ── Logo — width locked to sidebar ── */}
      <LogoSection onClick={() => router.push('/home')}>
        <LogoBox>A</LogoBox>
        <LogoText>ask<span>Data</span><span className="ai">AI</span></LogoText>
      </LogoSection>

      {/* ── Centre navigation ── */}
      <NavSection>
        {navItems.map(item => (
          <NavBtn
            key={item.path}
            $active={path.startsWith(item.path)}
            onClick={() => router.push(
              item.path === '/knowledge' ? '/knowledge/question-sql-pairs' : item.path
            )}
          >
            {item.label}
          </NavBtn>
        ))}
      </NavSection>

      {/* ── Right: deploy + connection ── */}
      <RightSection>
        {info.connected && needsRedeploy && (
          <>
            <PendingTag>⚡ Pending</PendingTag>
            <DeployBtn onClick={handleDeploy} disabled={deploying}>
              {deploying ? 'Deploying…' : 'Deploy'}
            </DeployBtn>
          </>
        )}
        <ConnBadge
          $on={info.connected}
          onClick={() => router.push('/settings')}
        >
          <Dot $on={info.connected} />
          {info.connected ? (info.database || 'Connected') : 'Disconnected'}
        </ConnBadge>
      </RightSection>
    </Header>
  );
}
