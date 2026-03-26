import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.amiddha.untangle',
  appName: 'Untangle',
  webDir: 'dist',
  server: {
    allowNavigation: ['time-estimation-agent-production.up.railway.app'],
  },
  ios: {
    contentInset: 'never',
    scrollEnabled: false,
  },
};

export default config;
