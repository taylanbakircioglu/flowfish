// Flowfish Frontend Application
// Version is managed by CI/CD pipeline via src/version.ts
import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { RootState } from './store';
import Layout from './components/Layout/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import ClusterManagement from './pages/ClusterManagement';
import AnalysisWizard from './pages/AnalysisWizard';
import AnalysisList from './pages/AnalysisList';
import ChangeDetection from './pages/ChangeDetection';
import ApplicationInventory from './pages/ApplicationInventory';
import Map from './pages/Map';
import ImpactSimulation from './pages/ImpactSimulation';
import NetworkExplorer from './pages/NetworkExplorer';
import ActivityMonitor from './pages/ActivityMonitor';
import SecurityCenter from './pages/SecurityCenter';
import EventsTimeline from './pages/EventsTimeline';
import Reports from './pages/Reports';
import DevConsole from './pages/DevConsole';
import Settings from './pages/Settings';
import UserManagement from './pages/UserManagement';
import BlastRadiusOracle from './pages/BlastRadiusOracle';
import APIDocumentation from './pages/APIDocumentation';
import AIIntegrationHub from './pages/AIIntegrationHub';

// Build Timestamp forces unique webpack hash on each build
const BUILD_TIMESTAMP = process.env.REACT_APP_BUILD_TIMESTAMP || 'dev';
console.log(`[Flowfish] Build: ${BUILD_TIMESTAMP}`);

// Protected Route component
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const isAuthenticated = useSelector((state: RootState) => state.auth.isAuthenticated);
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  
  return <>{children}</>;
};

const App: React.FC = () => {
  // Auth is now initialized in authSlice from localStorage
  // No need for useEffect - state is hydrated synchronously on store creation
  
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<Login />} />
      
      {/* Protected routes */}
      <Route path="/" element={
        <ProtectedRoute>
          <Layout />
        </ProtectedRoute>
      }>
        {/* Dashboard routes */}
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        
        {/* Analysis routes */}
        <Route path="analysis/wizard" element={<AnalysisWizard />} />
        <Route path="analyses" element={<AnalysisList />} />
        
        {/* Discovery routes */}
        <Route path="discovery/map" element={<Map />} />
        <Route path="discovery/network-explorer" element={<NetworkExplorer />} />
        <Route path="discovery/inventory" element={<ApplicationInventory />} />
        
        {/* Impact Analysis routes */}
        <Route path="impact/change-detection" element={<ChangeDetection />} />
        
        {/* Impact Analysis routes */}
        <Route path="impact/simulation" element={<ImpactSimulation />} />
        <Route path="impact/blast-radius" element={<BlastRadiusOracle />} />
        
        {/* AI Integration routes */}
        <Route path="integration/ai-hub" element={<AIIntegrationHub />} />
        
        {/* Observability routes */}
        <Route path="observability/activity" element={<ActivityMonitor />} />
        <Route path="observability/events" element={<EventsTimeline />} />
        
        {/* Security routes */}
        <Route path="security/center" element={<SecurityCenter />} />
        
        {/* Reports routes */}
        <Route path="reports" element={<Reports />} />
        
        {/* Management routes */}
        <Route path="management/clusters" element={<ClusterManagement />} />
        
        {/* Developer Tools */}
        <Route path="dev/console" element={<DevConsole />} />
        <Route path="dev/api-docs" element={<APIDocumentation />} />
        
        {/* Settings */}
        <Route path="settings" element={<Settings />} />
        
        {/* User Management */}
        <Route path="management/users" element={<UserManagement />} />
        
        {/* Catch all */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
};

export default App;
