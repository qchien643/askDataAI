import { ReactNode } from 'react';
import styled from 'styled-components';
import HeaderBar from './HeaderBar';

/* ══════════════════════════════════════════════════════
   LAYOUT WRAPPER
   ══════════════════════════════════════════════════════ */
const Wrapper = styled.div`
  min-height: 100vh;
  padding-top: var(--header-h, 56px);   /* reserve space for fixed header */
  background: var(--m-bg);
`;

const Body = styled.div`
  display: flex;
  /* fill viewport below fixed header */
  height: calc(100vh - var(--header-h, 56px));
  overflow: hidden;
`;

/* ══════════════════════════════════════════════════════
   SIDEBAR
   • Width = var(--sidebar-w, 260px)  ← matches LogoSection in HeaderBar
   • Left border colour accent bar = 4px yellow strip
   • Border-right = 3px black  ← meets header border-bottom at corner
   ══════════════════════════════════════════════════════ */
const Sider = styled.aside`
  width: var(--sidebar-w, 260px);
  min-width: var(--sidebar-w, 260px);
  background: var(--m-black);
  /* Right border — visually continues the header bottom-border downward */
  border-right: 3px solid var(--m-black);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  flex-shrink: 0;

  /* Subtle diagonal stripe texture */
  &::after {
    content: '';
    position: absolute;
    inset: 0;
    background: repeating-linear-gradient(
      -45deg,
      transparent,
      transparent 12px,
      rgba(255,255,255,0.015) 12px,
      rgba(255,255,255,0.015) 24px
    );
    pointer-events: none;
    z-index: 0;
  }
`;

const SiderScrollArea = styled.div`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  position: relative;
  z-index: 1;

  /* Sidebar custom scrollbar */
  &::-webkit-scrollbar { width: 3px; }
  &::-webkit-scrollbar-thumb { background: rgba(255,230,0,0.4); border-radius: 0; }
  &::-webkit-scrollbar-track { background: transparent; }
`;

/* Memphis decorative shapes at sidebar bottom */
const SideDecorCircle = styled.div`
  position: absolute;
  bottom: 60px; right: -30px;
  width: 80px; height: 80px;
  border: 3px solid rgba(255,51,102,0.20);
  border-radius: 50%;
  pointer-events: none;
  z-index: 0;
`;
const SideDecorSquare = styled.div`
  position: absolute;
  bottom: 90px; left: 20px;
  width: 24px; height: 24px;
  background: rgba(255,230,0,0.10);
  border: 2px solid rgba(255,230,0,0.20);
  pointer-events: none;
  z-index: 0;
`;

const SiderFooter = styled.div`
  border-top: 2px solid rgba(255,255,255,0.08);
  position: relative;
  z-index: 2;
`;

const FooterBtn = styled.button`
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: transparent;
  border: none;
  color: rgba(255,255,255,0.4);
  font-size: 10px;
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  cursor: pointer;
  transition: all 0.1s;

  &:hover {
    color: var(--m-yellow);
    background: rgba(255,230,0,0.06);
  }
`;

/* ══════════════════════════════════════════════════════
   MAIN CONTENT
   ══════════════════════════════════════════════════════ */
const Content = styled.main`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  background: var(--m-bg);
  position: relative;

  /* Main area scrollbar */
  &::-webkit-scrollbar { width: 6px; }
  &::-webkit-scrollbar-thumb { background: var(--m-black); }
  &::-webkit-scrollbar-track { background: var(--m-bg-2); }
`;

/* ══════════════════════════════════════════════════════
   COMPONENT
   ══════════════════════════════════════════════════════ */
interface Props {
  children: ReactNode;
  sidebar?: ReactNode;
}

export default function SiderLayout({ children, sidebar }: Props) {
  return (
    <Wrapper>
      <HeaderBar />

      <Body>
        {sidebar && (
          <Sider>
            <SiderScrollArea>{sidebar}</SiderScrollArea>

            {/* Memphis decorations */}
            <SideDecorCircle />
            <SideDecorSquare />

            <SiderFooter>
              <FooterBtn onClick={() => (window.location.href = '/settings')}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="2.5">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
                Settings
              </FooterBtn>
            </SiderFooter>
          </Sider>
        )}

        <Content>{children}</Content>
      </Body>
    </Wrapper>
  );
}
