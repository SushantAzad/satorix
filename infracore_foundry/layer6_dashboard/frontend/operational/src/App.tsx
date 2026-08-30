import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import SystemHealth from './pages/SystemHealth'
import KafkaMonitor from './pages/KafkaMonitor'
import SourceHealth from './pages/SourceHealth'
import IngestionQueue from './pages/IngestionQueue'
import OntologyHealth from './pages/OntologyHealth'
import ModelPerformance from './pages/ModelPerformance'
import AlertAnalytics from './pages/AlertAnalytics'
import CsvImport from '../../intelligence/src/pages/CsvImport'
import Login from './pages/Login'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Layout />}>
          <Route index element={<SystemHealth />} />
          <Route path="kafka" element={<KafkaMonitor />} />
          <Route path="sources" element={<SourceHealth />} />
          <Route path="ingestion" element={<IngestionQueue />} />
          <Route path="imports" element={<CsvImport />} />
          <Route path="ontology" element={<OntologyHealth />} />
          <Route path="models" element={<ModelPerformance />} />
          <Route path="alerts-analytics" element={<AlertAnalytics />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
