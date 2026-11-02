import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './style.css';

// 挂载开发工作台，严格模式帮助发现组件生命周期问题。
createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
);
