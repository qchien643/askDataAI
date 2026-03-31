import { ReactNode } from 'react';
import styled from 'styled-components';
import HeaderBar from './HeaderBar';

const Wrapper = styled.div`
  min-height: 100vh;
  padding-top: 48px;
`;

const Body = styled.div`
  display: flex;
  height: calc(100vh - 48px);
`;

const Sider = styled.aside`
  width: 280px;
  min-width: 280px;
  background: #fafafa;
  border-right: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`;

const SiderContent = styled.div`
  flex: 1;
  overflow-y: auto;
`;

const SiderFooter = styled.div`
  border-top: 1px solid #f0f0f0;
  padding: 8px 0;
`;

const FooterButton = styled.button`
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  background: transparent;
  border: none;
  color: #65676c;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;

  &:hover {
    background: #f0f0f0;
  }
`;

const Content = styled.main`
  flex: 1;
  overflow-y: auto;
  background: white;
`;

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
            <SiderContent>{sidebar}</SiderContent>
            <SiderFooter>
              <FooterButton onClick={() => window.location.href = '/settings'}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                Settings
              </FooterButton>
            </SiderFooter>
          </Sider>
        )}
        <Content>{children}</Content>
      </Body>
    </Wrapper>
  );
}
