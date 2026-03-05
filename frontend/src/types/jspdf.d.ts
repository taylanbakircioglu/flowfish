// Type declarations for jspdf and jspdf-autotable

declare module 'jspdf' {
  export interface jsPDFOptions {
    orientation?: 'portrait' | 'landscape' | 'p' | 'l';
    unit?: 'pt' | 'px' | 'in' | 'mm' | 'cm' | 'ex' | 'em' | 'pc';
    format?: string | number[];
    compress?: boolean;
    precision?: number;
    userUnit?: number;
    hotfixes?: string[];
    encryption?: {
      userPassword?: string;
      ownerPassword?: string;
      userPermissions?: string[];
    };
    putOnlyUsedFonts?: boolean;
    floatPrecision?: number | 'smart';
  }

  export class jsPDF {
    constructor(options?: jsPDFOptions);
    constructor(orientation?: 'portrait' | 'landscape' | 'p' | 'l', unit?: string, format?: string | number[], compress?: boolean);
    
    text(text: string | string[], x: number, y: number, options?: any): jsPDF;
    setFontSize(size: number): jsPDF;
    setFont(fontName: string, fontStyle?: string, fontWeight?: string | number): jsPDF;
    setTextColor(r: number, g?: number, b?: number): jsPDF;
    setDrawColor(r: number, g?: number, b?: number): jsPDF;
    setFillColor(r: number, g?: number, b?: number): jsPDF;
    rect(x: number, y: number, w: number, h: number, style?: string): jsPDF;
    line(x1: number, y1: number, x2: number, y2: number): jsPDF;
    addPage(format?: string | number[], orientation?: string): jsPDF;
    save(filename: string, options?: any): jsPDF;
    output(type?: string, options?: any): any;
    getNumberOfPages(): number;
    setPage(page: number): jsPDF;
    internal: {
      pageSize: {
        width: number;
        height: number;
        getWidth: () => number;
        getHeight: () => number;
      };
      getNumberOfPages: () => number;
    };
    
    // For autoTable plugin
    autoTable: (options: AutoTableOptions) => jsPDF;
    lastAutoTable?: {
      finalY: number;
    };
    previousAutoTable?: {
      finalY: number;
    };
  }

  export default jsPDF;
}

declare module 'jspdf-autotable' {
  import jsPDF from 'jspdf';

  interface CellDef {
    content?: string | number;
    rowSpan?: number;
    colSpan?: number;
    styles?: Partial<Styles>;
  }

  interface Styles {
    font?: string;
    fontStyle?: string;
    overflow?: 'linebreak' | 'ellipsize' | 'visible' | 'hidden';
    fillColor?: string | number | number[];
    textColor?: string | number | number[];
    halign?: 'left' | 'center' | 'right' | 'justify';
    valign?: 'top' | 'middle' | 'bottom';
    fontSize?: number;
    cellPadding?: number | { top: number; right: number; bottom: number; left: number };
    lineColor?: string | number | number[];
    lineWidth?: number;
    cellWidth?: 'auto' | 'wrap' | number;
    minCellHeight?: number;
    minCellWidth?: number;
  }

  interface ColumnDef {
    header?: string | CellDef;
    dataKey?: string | number;
    footer?: string | CellDef;
  }

  interface UserOptions {
    head?: (string | CellDef)[][];
    body?: (string | number | CellDef)[][];
    foot?: (string | CellDef)[][];
    columns?: ColumnDef[];
    startY?: number;
    margin?: number | { top?: number; right?: number; bottom?: number; left?: number };
    pageBreak?: 'auto' | 'avoid' | 'always';
    rowPageBreak?: 'auto' | 'avoid';
    tableWidth?: 'auto' | 'wrap' | number;
    showHead?: 'everyPage' | 'firstPage' | 'never';
    showFoot?: 'everyPage' | 'lastPage' | 'never';
    tableLineWidth?: number;
    tableLineColor?: string | number | number[];
    theme?: 'striped' | 'grid' | 'plain';
    styles?: Partial<Styles>;
    headStyles?: Partial<Styles>;
    bodyStyles?: Partial<Styles>;
    footStyles?: Partial<Styles>;
    alternateRowStyles?: Partial<Styles>;
    columnStyles?: { [key: string]: Partial<Styles> };
    didParseCell?: (data: any) => void;
    willDrawCell?: (data: any) => void;
    didDrawCell?: (data: any) => void;
    didDrawPage?: (data: any) => void;
  }

  export default function autoTable(doc: jsPDF, options: UserOptions): void;
}

// Global type for AutoTableOptions used by jsPDF.autoTable method
interface AutoTableOptions {
  head?: (string | { content?: string | number; rowSpan?: number; colSpan?: number; styles?: any })[][];
  body?: (string | number | { content?: string | number; rowSpan?: number; colSpan?: number; styles?: any })[][];
  foot?: (string | { content?: string | number; rowSpan?: number; colSpan?: number; styles?: any })[][];
  columns?: { header?: string; dataKey?: string | number; footer?: string }[];
  startY?: number;
  margin?: number | { top?: number; right?: number; bottom?: number; left?: number };
  pageBreak?: 'auto' | 'avoid' | 'always';
  rowPageBreak?: 'auto' | 'avoid';
  tableWidth?: 'auto' | 'wrap' | number;
  showHead?: 'everyPage' | 'firstPage' | 'never';
  showFoot?: 'everyPage' | 'lastPage' | 'never';
  theme?: 'striped' | 'grid' | 'plain';
  styles?: any;
  headStyles?: any;
  bodyStyles?: any;
  footStyles?: any;
  alternateRowStyles?: any;
  columnStyles?: { [key: string]: any };
  didParseCell?: (data: any) => void;
  willDrawCell?: (data: any) => void;
  didDrawCell?: (data: any) => void;
  didDrawPage?: (data: any) => void;
}
