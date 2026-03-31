import type { AppProps } from 'next/app';
import { ConfigProvider } from 'antd';
import theme from '@/styles/theme';
import { ConnectionProvider } from '@/contexts/ConnectionContext';
import { ChatProvider } from '@/contexts/ChatContext';
import '@/styles/globals.css';

export default function App({ Component, pageProps }: AppProps) {
  return (
    <ConfigProvider theme={theme}>
      <ConnectionProvider>
        <ChatProvider>
          <Component {...pageProps} />
        </ChatProvider>
      </ConnectionProvider>
    </ConfigProvider>
  );
}
