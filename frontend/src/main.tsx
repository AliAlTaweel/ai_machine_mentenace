import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { logger } from './lib/logger';
import './index.css';

window.addEventListener('error', (event) => {
  logger.error('Uncaught error', {
    message: event.message,
    filename: event.filename,
    lineno: event.lineno,
  });
});

window.addEventListener('unhandledrejection', (event) => {
  logger.error('Unhandled promise rejection', { reason: String(event.reason) });
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
