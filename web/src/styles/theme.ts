import type { ThemeConfig } from 'antd';

const theme: ThemeConfig = {
  token: {
    colorPrimary: '#4B6BFB',
    borderRadius: 4,
    fontFamily: "'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    colorBgContainer: '#ffffff',
    colorBgLayout: '#fafafa',
    colorText: '#262626',
    colorTextSecondary: '#65676c',
    colorTextTertiary: '#8c8c8c',
    colorBorder: '#d9d9d9',
    colorSplit: '#f0f0f0',
  },
  components: {
    Layout: {
      headerBg: '#262626',
      headerHeight: 48,
      siderBg: '#fafafa',
    },
    Button: {
      borderRadius: 4,
    },
    Table: {
      headerBg: '#fafafa',
      borderColor: '#f0f0f0',
    },
    Drawer: {
      paddingLG: 24,
    },
  },
};

export default theme;
