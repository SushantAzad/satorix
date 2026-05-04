import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import SystemHealth from './pages/SystemHealth'
import KafkaMonitor from './pages/KafkaMonitor'
import SourceHealth from './pages/SourceHealth'
import IngestionQueue from './pages/IngestionQueue'
import OntologyHealth from './pages/OntologyHealth'
import ModelPerformance from './pages/ModelPerformance'
import AlertAnalytics from './pages/AlertAnalytics'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<SystemHealth />} />
          <Route path="kafka" element={<KafkaMonitor />} />
          <Route path="sources" element={<SourceHealth />} />
          <Route path="ingestion" element={<IngestionQueue />} />
          <Route path="ontology" element={<OntologyHealth />} />
          <Route path="models" element={<ModelPerformance />} />
          <Route path="alerts-analytics" element={<AlertAnalytics />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
