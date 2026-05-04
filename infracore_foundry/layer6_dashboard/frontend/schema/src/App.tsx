import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import ObjectTypes from './pages/ObjectTypes'
import SchemaVersions from './pages/SchemaVersions'
import DataQuality from './pages/DataQuality'
import FunctionTester from './pages/FunctionTester'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<ObjectTypes />} />
          <Route path="versions" element={<SchemaVersions />} />
          <Route path="quality" element={<DataQuality />} />
          <Route path="function-tester" element={<FunctionTester />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
