/**
 * Export Utilities for Change Detection Reports
 * 
 * Supports: CSV, JSON, PDF, Excel
 */

import dayjs from 'dayjs';
import type { Change, ChangeStats, SnapshotComparison } from '../store/api/changesApi';

// Change type labels for export - organized by category
const changeTypeLabels: Record<string, string> = {
  // Legacy types
  workload_added: 'Workload Added',
  workload_removed: 'Workload Removed',
  namespace_changed: 'Namespace Changed',
  // Infrastructure changes (K8s API)
  replica_changed: 'Replica Changed',
  config_changed: 'Config Changed',
  image_changed: 'Image Changed',
  label_changed: 'Label Changed',
  // Connection changes (eBPF)
  connection_added: 'Connection Added',
  port_changed: 'Port Changed',
  // Anomaly detection (eBPF)
  connection_removed: 'Connection Anomaly',
  traffic_anomaly: 'Traffic Anomaly',
  dns_anomaly: 'DNS Anomaly',
  process_anomaly: 'Process Anomaly',
  error_anomaly: 'Error Anomaly',
};

// Risk level labels
const riskLabels: Record<string, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

export interface ExportData {
  changes: Change[];
  stats?: ChangeStats;
  comparison?: SnapshotComparison;
  metadata?: {
    clusterId?: number;
    analysisId?: number;
    exportTime: string;
    dateRange?: { start: string; end: string };
  };
}

/**
 * Export changes to CSV format
 */
export function exportToCSV(data: ExportData, filename?: string): void {
  const { changes, metadata } = data;
  
  // CSV header
  const headers = [
    'ID',
    'Timestamp',
    'Change Type',
    'Target',
    'Namespace',
    'Details',
    'Risk Level',
    'Affected Services',
    'Changed By',
  ];
  
  // CSV rows
  const rows = changes.map(change => [
    change.id,
    dayjs(change.timestamp).format('YYYY-MM-DD HH:mm:ss'),
    changeTypeLabels[change.change_type] || change.change_type,
    change.target,
    change.namespace,
    `"${(change.details || '').replace(/"/g, '""')}"`, // Escape quotes
    riskLabels[change.risk] || change.risk,
    change.affected_services,
    change.changed_by,
  ]);
  
  // Build CSV content
  let csvContent = '';
  
  // Add metadata as comments
  if (metadata) {
    csvContent += `# Flowfish Change Detection Report\n`;
    csvContent += `# Export Time: ${metadata.exportTime}\n`;
    if (metadata.clusterId) csvContent += `# Cluster ID: ${metadata.clusterId}\n`;
    if (metadata.analysisId) csvContent += `# Analysis ID: ${metadata.analysisId}\n`;
    if (metadata.dateRange) {
      csvContent += `# Date Range: ${metadata.dateRange.start} to ${metadata.dateRange.end}\n`;
    }
    csvContent += `# Total Changes: ${changes.length}\n`;
    csvContent += `#\n`;
  }
  
  csvContent += headers.join(',') + '\n';
  csvContent += rows.map(row => row.join(',')).join('\n');
  
  // Download
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  downloadBlob(blob, filename || `changes-${dayjs().format('YYYY-MM-DD-HHmmss')}.csv`);
}

/**
 * Export changes to JSON format
 */
export function exportToJSON(data: ExportData, filename?: string): void {
  const exportObject = {
    metadata: {
      ...data.metadata,
      format: 'Flowfish Change Detection Export',
      version: '1.0',
    },
    summary: {
      totalChanges: data.changes.length,
      stats: data.stats,
      comparison: data.comparison,
    },
    changes: data.changes.map(change => ({
      ...change,
      change_type_label: changeTypeLabels[change.change_type],
      risk_label: riskLabels[change.risk],
    })),
  };
  
  const jsonContent = JSON.stringify(exportObject, null, 2);
  const blob = new Blob([jsonContent], { type: 'application/json' });
  downloadBlob(blob, filename || `changes-${dayjs().format('YYYY-MM-DD-HHmmss')}.json`);
}

/**
 * Export changes to Excel format (XLSX)
 * Uses a simple XML-based approach that Excel can open
 */
export function exportToExcel(data: ExportData, filename?: string): void {
  const { changes, stats, comparison, metadata } = data;
  
  // Build Excel XML (Office Open XML simplified)
  let xml = '<?xml version="1.0" encoding="UTF-8"?>\n';
  xml += '<?mso-application progid="Excel.Sheet"?>\n';
  xml += '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"\n';
  xml += '  xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">\n';
  
  // Styles
  xml += '<Styles>\n';
  xml += '  <Style ss:ID="Header"><Font ss:Bold="1"/><Interior ss:Color="#F0F0F0" ss:Pattern="Solid"/></Style>\n';
  xml += '  <Style ss:ID="Critical"><Interior ss:Color="#FFCCCC" ss:Pattern="Solid"/></Style>\n';
  xml += '  <Style ss:ID="High"><Interior ss:Color="#FFE6CC" ss:Pattern="Solid"/></Style>\n';
  xml += '  <Style ss:ID="Medium"><Interior ss:Color="#FFFFCC" ss:Pattern="Solid"/></Style>\n';
  xml += '  <Style ss:ID="Low"><Interior ss:Color="#CCFFCC" ss:Pattern="Solid"/></Style>\n';
  xml += '</Styles>\n';
  
  // Changes Worksheet
  xml += '<Worksheet ss:Name="Changes">\n';
  xml += '<Table>\n';
  
  // Header row
  xml += '<Row ss:StyleID="Header">\n';
  ['ID', 'Timestamp', 'Change Type', 'Target', 'Namespace', 'Details', 'Risk', 'Affected Services', 'Changed By'].forEach(h => {
    xml += `  <Cell><Data ss:Type="String">${escapeXml(h)}</Data></Cell>\n`;
  });
  xml += '</Row>\n';
  
  // Data rows
  changes.forEach(change => {
    const styleId = change.risk.charAt(0).toUpperCase() + change.risk.slice(1);
    xml += `<Row ss:StyleID="${styleId}">\n`;
    xml += `  <Cell><Data ss:Type="Number">${change.id}</Data></Cell>\n`;
    xml += `  <Cell><Data ss:Type="String">${dayjs(change.timestamp).format('YYYY-MM-DD HH:mm:ss')}</Data></Cell>\n`;
    xml += `  <Cell><Data ss:Type="String">${escapeXml(changeTypeLabels[change.change_type] || change.change_type)}</Data></Cell>\n`;
    xml += `  <Cell><Data ss:Type="String">${escapeXml(change.target)}</Data></Cell>\n`;
    xml += `  <Cell><Data ss:Type="String">${escapeXml(change.namespace)}</Data></Cell>\n`;
    xml += `  <Cell><Data ss:Type="String">${escapeXml(change.details || '')}</Data></Cell>\n`;
    xml += `  <Cell><Data ss:Type="String">${escapeXml(riskLabels[change.risk] || change.risk)}</Data></Cell>\n`;
    xml += `  <Cell><Data ss:Type="Number">${change.affected_services}</Data></Cell>\n`;
    xml += `  <Cell><Data ss:Type="String">${escapeXml(change.changed_by)}</Data></Cell>\n`;
    xml += '</Row>\n';
  });
  
  xml += '</Table>\n';
  xml += '</Worksheet>\n';
  
  // Summary Worksheet
  if (stats || comparison) {
    xml += '<Worksheet ss:Name="Summary">\n';
    xml += '<Table>\n';
    
    // Metadata
    xml += '<Row ss:StyleID="Header"><Cell><Data ss:Type="String">Report Summary</Data></Cell></Row>\n';
    xml += '<Row><Cell><Data ss:Type="String">Export Time</Data></Cell>';
    xml += `<Cell><Data ss:Type="String">${metadata?.exportTime || dayjs().toISOString()}</Data></Cell></Row>\n`;
    xml += `<Row><Cell><Data ss:Type="String">Total Changes</Data></Cell>`;
    xml += `<Cell><Data ss:Type="Number">${changes.length}</Data></Cell></Row>\n`;
    
    if (stats) {
      xml += '<Row><Cell/></Row>\n'; // Empty row
      xml += '<Row ss:StyleID="Header"><Cell><Data ss:Type="String">By Risk Level</Data></Cell></Row>\n';
      Object.entries(stats.by_risk).forEach(([risk, count]) => {
        xml += `<Row><Cell><Data ss:Type="String">${riskLabels[risk] || risk}</Data></Cell>`;
        xml += `<Cell><Data ss:Type="Number">${count}</Data></Cell></Row>\n`;
      });
      
      xml += '<Row><Cell/></Row>\n';
      xml += '<Row ss:StyleID="Header"><Cell><Data ss:Type="String">By Change Type</Data></Cell></Row>\n';
      Object.entries(stats.by_type).forEach(([type, count]) => {
        xml += `<Row><Cell><Data ss:Type="String">${changeTypeLabels[type] || type}</Data></Cell>`;
        xml += `<Cell><Data ss:Type="Number">${count}</Data></Cell></Row>\n`;
      });
    }
    
    if (comparison) {
      xml += '<Row><Cell/></Row>\n';
      xml += '<Row ss:StyleID="Header"><Cell><Data ss:Type="String">Comparison</Data></Cell></Row>\n';
      xml += `<Row><Cell><Data ss:Type="String">Additions</Data></Cell>`;
      xml += `<Cell><Data ss:Type="Number">${comparison.summary.added}</Data></Cell></Row>\n`;
      xml += `<Row><Cell><Data ss:Type="String">Removals</Data></Cell>`;
      xml += `<Cell><Data ss:Type="Number">${comparison.summary.removed}</Data></Cell></Row>\n`;
      xml += `<Row><Cell><Data ss:Type="String">Modifications</Data></Cell>`;
      xml += `<Cell><Data ss:Type="Number">${comparison.summary.modified}</Data></Cell></Row>\n`;
    }
    
    xml += '</Table>\n';
    xml += '</Worksheet>\n';
  }
  
  xml += '</Workbook>';
  
  const blob = new Blob([xml], { type: 'application/vnd.ms-excel' });
  downloadBlob(blob, filename || `changes-${dayjs().format('YYYY-MM-DD-HHmmss')}.xls`);
}

/**
 * Export changes to PDF format
 * Creates a printable HTML that opens in a new window for PDF save
 */
export function exportToPDF(data: ExportData, filename?: string): void {
  const { changes, stats, comparison, metadata } = data;
  
  // Build HTML for PDF
  const html = `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Change Detection Report</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      margin: 40px;
      color: #333;
    }
    h1 { color: #0891b2; border-bottom: 2px solid #0891b2; padding-bottom: 10px; }
    h2 { color: #555; margin-top: 30px; }
    .meta { background: #f5f5f5; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
    .meta p { margin: 5px 0; }
    .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 30px; }
    .stat-card { background: #fafafa; padding: 15px; border-radius: 8px; text-align: center; }
    .stat-value { font-size: 24px; font-weight: bold; color: #0891b2; }
    .stat-label { font-size: 12px; color: #888; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th { background: #0891b2; color: white; padding: 12px 8px; text-align: left; font-size: 12px; }
    td { padding: 10px 8px; border-bottom: 1px solid #eee; font-size: 11px; }
    tr:hover { background: #f5f5f5; }
    .risk-critical { background: #fff1f0; color: #cf1322; font-weight: bold; }
    .risk-high { background: #fff7e6; color: #b89b5d; }
    .risk-medium { background: #fffbe6; color: #c9a55a; }
    .risk-low { background: #f6ffed; color: #4d9f7c; }
    .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; }
    @media print {
      body { margin: 20px; }
      .no-print { display: none; }
    }
  </style>
</head>
<body>
  <div class="no-print" style="margin-bottom: 20px; padding: 10px; background: #e6f7ff; border-radius: 4px;">
    <strong>Tip:</strong> Press Ctrl+P (or Cmd+P) to print or save as PDF
  </div>
  
  <h1>🔄 Change Detection Report</h1>
  
  <div class="meta">
    <p><strong>Generated:</strong> ${metadata?.exportTime || dayjs().format('YYYY-MM-DD HH:mm:ss')}</p>
    ${metadata?.clusterId ? `<p><strong>Cluster ID:</strong> ${metadata.clusterId}</p>` : ''}
    ${metadata?.analysisId ? `<p><strong>Analysis ID:</strong> ${metadata.analysisId}</p>` : ''}
    ${metadata?.dateRange ? `<p><strong>Period:</strong> ${metadata.dateRange.start} to ${metadata.dateRange.end}</p>` : ''}
    <p><strong>Total Changes:</strong> ${changes.length}</p>
  </div>
  
  ${stats ? `
  <h2>📊 Summary Statistics</h2>
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-value">${stats.total_changes}</div>
      <div class="stat-label">Total Changes</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: #cf1322">${stats.by_risk.critical || 0}</div>
      <div class="stat-label">Critical</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: #c75450">${stats.by_risk.high || 0}</div>
      <div class="stat-label">High Risk</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color: #4d9f7c">${comparison?.summary.added || 0}</div>
      <div class="stat-label">Additions</div>
    </div>
  </div>
  ` : ''}
  
  <h2>📋 Change Details</h2>
  <table>
    <thead>
      <tr>
        <th>Time</th>
        <th>Type</th>
        <th>Target</th>
        <th>Namespace</th>
        <th>Details</th>
        <th>Risk</th>
        <th>Impact</th>
      </tr>
    </thead>
    <tbody>
      ${changes.map(change => `
        <tr class="risk-${change.risk}">
          <td>${dayjs(change.timestamp).format('MM-DD HH:mm')}</td>
          <td><span class="tag" style="background: #e6f7ff">${changeTypeLabels[change.change_type] || change.change_type}</span></td>
          <td><strong>${escapeHtml(change.target)}</strong></td>
          <td>${escapeHtml(change.namespace)}</td>
          <td>${escapeHtml(change.details || '-')}</td>
          <td><span class="tag risk-${change.risk}">${riskLabels[change.risk]}</span></td>
          <td>${change.affected_services} services</td>
        </tr>
      `).join('')}
    </tbody>
  </table>
  
  <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; color: #888; font-size: 11px;">
    <p>Generated by Flowfish Change Detection • ${dayjs().format('YYYY-MM-DD HH:mm:ss')}</p>
  </div>
</body>
</html>
  `;
  
  // Open in new window for printing
  const printWindow = window.open('', '_blank');
  if (printWindow) {
    printWindow.document.write(html);
    printWindow.document.close();
  }
}

/**
 * Helper: Download blob as file
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Helper: Escape XML special characters
 */
function escapeXml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/**
 * Helper: Escape HTML special characters
 */
function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export type ExportFormat = 'csv' | 'json' | 'excel' | 'pdf';

/**
 * Export changes in specified format
 */
export function exportChanges(
  format: ExportFormat,
  data: ExportData,
  filename?: string
): void {
  switch (format) {
    case 'csv':
      exportToCSV(data, filename);
      break;
    case 'json':
      exportToJSON(data, filename);
      break;
    case 'excel':
      exportToExcel(data, filename);
      break;
    case 'pdf':
      exportToPDF(data, filename);
      break;
    default:
      console.error(`Unknown export format: ${format}`);
  }
}
