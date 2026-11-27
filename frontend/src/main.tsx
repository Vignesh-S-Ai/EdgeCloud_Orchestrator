import React from 'react';
import ReactDOM from 'react-dom/client';
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-500.css';
import '@fontsource/inter/latin-600.css';
import '@fontsource/inter/latin-700.css';
import './index.css';
import App from './App';
import { DataSourceProvider } from './context/DataSourceContext';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <DataSourceProvider>
      <App />
    </DataSourceProvider>
  </React.StrictMode>,
);
