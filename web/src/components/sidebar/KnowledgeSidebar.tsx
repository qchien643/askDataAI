import { ReactNode } from 'react';
import { useRouter } from 'next/router';
import styled from 'styled-components';

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
  font-weight: ${p => p.$active ? 500 : 400};
  &:hover { background: ${p => p.$active ? '#d9d9d9' : '#f0f0f0'}; }
`;

export default function KnowledgeSidebar() {
  const router = useRouter();
  const path = router.pathname;

  const items = [
    { label: 'Question-SQL Pairs', path: '/knowledge/question-sql-pairs' },
    { label: 'Business Glossary', path: '/knowledge/glossary' },
  ];

  return (
    <SidebarSection>
      <SidebarLabel>Knowledge</SidebarLabel>
      {items.map(item => (
        <MenuItem
          key={item.path}
          $active={path === item.path}
          onClick={() => router.push(item.path)}
        >
          {item.label}
        </MenuItem>
      ))}
    </SidebarSection>
  );
}
