// Type declarations for @xyflow/react v12.9.3
declare module '@xyflow/react' {
  import { ComponentType, CSSProperties, ReactNode, MouseEvent, WheelEvent, TouchEvent } from 'react';

  export interface XYPosition {
    x: number;
    y: number;
  }

  export interface Viewport {
    x: number;
    y: number;
    zoom: number;
  }

  export interface Node<T = any> {
    id: string;
    type?: string;
    position: XYPosition;
    data: T;
    style?: CSSProperties;
    className?: string;
    selected?: boolean;
    draggable?: boolean;
    selectable?: boolean;
    connectable?: boolean;
    deletable?: boolean;
    hidden?: boolean;
    width?: number;
    height?: number;
    parentId?: string;
    zIndex?: number;
    extent?: 'parent' | [[number, number], [number, number]];
    expandParent?: boolean;
    dragHandle?: string;
  }

  export interface Edge<T = any> {
    id: string;
    source: string;
    target: string;
    sourceHandle?: string;
    targetHandle?: string;
    type?: string;
    data?: T;
    style?: CSSProperties;
    className?: string;
    label?: ReactNode;
    labelStyle?: CSSProperties;
    labelBgStyle?: CSSProperties;
    labelBgPadding?: [number, number];
    labelBgBorderRadius?: number;
    markerEnd?: any;
    markerStart?: any;
    animated?: boolean;
    selected?: boolean;
    hidden?: boolean;
    deletable?: boolean;
    focusable?: boolean;
    interactionWidth?: number;
  }

  export interface Connection {
    source: string | null;
    target: string | null;
    sourceHandle: string | null;
    targetHandle: string | null;
  }

  export type OnConnect = (connection: Connection) => void;
  export type OnNodesChange = (changes: any[]) => void;
  export type OnEdgesChange = (changes: any[]) => void;

  export interface ReactFlowInstance<NodeType = Node, EdgeType = Edge> {
    fitView: (options?: FitViewOptions) => void;
    zoomIn: (options?: { duration?: number }) => void;
    zoomOut: (options?: { duration?: number }) => void;
    setZoom: (zoom: number, options?: { duration?: number }) => void;
    getZoom: () => number;
    setViewport: (viewport: Viewport, options?: { duration?: number }) => void;
    getViewport: () => Viewport;
    setCenter: (x: number, y: number, options?: { zoom?: number; duration?: number }) => void;
    getNodes: () => NodeType[];
    getNode: (id: string) => NodeType | undefined;
    getEdges: () => EdgeType[];
    getEdge: (id: string) => EdgeType | undefined;
    setNodes: (nodes: NodeType[] | ((nodes: NodeType[]) => NodeType[])) => void;
    setEdges: (edges: EdgeType[] | ((edges: EdgeType[]) => EdgeType[])) => void;
    addNodes: (nodes: NodeType | NodeType[]) => void;
    addEdges: (edges: EdgeType | EdgeType[]) => void;
    toObject: () => { nodes: NodeType[]; edges: EdgeType[]; viewport: Viewport };
    deleteElements: (params: { nodes?: NodeType[]; edges?: EdgeType[] }) => void;
    screenToFlowPosition: (position: XYPosition) => XYPosition;
    flowToScreenPosition: (position: XYPosition) => XYPosition;
  }

  export interface FitViewOptions {
    padding?: number;
    includeHiddenNodes?: boolean;
    minZoom?: number;
    maxZoom?: number;
    duration?: number;
    nodes?: Node[];
  }

  export function useNodesState<T = any>(
    initialNodes: Node<T>[]
  ): [Node<T>[], (nodes: Node<T>[] | ((nodes: Node<T>[]) => Node<T>[])) => void, OnNodesChange];

  export function useEdgesState<T = any>(
    initialEdges: Edge<T>[]
  ): [Edge<T>[], (edges: Edge<T>[] | ((edges: Edge<T>[]) => Edge<T>[])) => void, OnEdgesChange];

  export function addEdge(connection: Connection | Edge, edges: Edge[]): Edge[];
  
  export function useReactFlow<NodeType = Node, EdgeType = Edge>(): ReactFlowInstance<NodeType, EdgeType>;

  export interface ReactFlowProps<NodeType = Node, EdgeType = Edge> {
    nodes?: NodeType[];
    edges?: EdgeType[];
    defaultNodes?: NodeType[];
    defaultEdges?: EdgeType[];
    onNodesChange?: OnNodesChange;
    onEdgesChange?: OnEdgesChange;
    onConnect?: OnConnect;
    onInit?: (instance: ReactFlowInstance<NodeType, EdgeType>) => void;
    onNodeClick?: (event: MouseEvent, node: NodeType) => void;
    onNodeDoubleClick?: (event: MouseEvent, node: NodeType) => void;
    onNodeDragStart?: (event: MouseEvent, node: NodeType, nodes: NodeType[]) => void;
    onNodeDrag?: (event: MouseEvent, node: NodeType, nodes: NodeType[]) => void;
    onNodeDragStop?: (event: MouseEvent, node: NodeType, nodes: NodeType[]) => void;
    onNodeMouseEnter?: (event: MouseEvent, node: NodeType) => void;
    onNodeMouseMove?: (event: MouseEvent, node: NodeType) => void;
    onNodeMouseLeave?: (event: MouseEvent, node: NodeType) => void;
    onEdgeClick?: (event: MouseEvent, edge: EdgeType) => void;
    onEdgeDoubleClick?: (event: MouseEvent, edge: EdgeType) => void;
    onEdgeMouseEnter?: (event: MouseEvent, edge: EdgeType) => void;
    onEdgeMouseMove?: (event: MouseEvent, edge: EdgeType) => void;
    onEdgeMouseLeave?: (event: MouseEvent, edge: EdgeType) => void;
    onMove?: (event: MouseEvent | TouchEvent | null, viewport: Viewport) => void;
    onMoveStart?: (event: MouseEvent | TouchEvent | null, viewport: Viewport) => void;
    onMoveEnd?: (event: MouseEvent | TouchEvent | null, viewport: Viewport) => void;
    onPaneClick?: (event: MouseEvent) => void;
    onPaneScroll?: (event: WheelEvent) => void;
    onPaneContextMenu?: (event: MouseEvent) => void;
    fitView?: boolean;
    fitViewOptions?: FitViewOptions;
    minZoom?: number;
    maxZoom?: number;
    defaultViewport?: Viewport;
    snapToGrid?: boolean;
    snapGrid?: [number, number];
    nodesDraggable?: boolean;
    nodesConnectable?: boolean;
    nodesFocusable?: boolean;
    edgesFocusable?: boolean;
    elementsSelectable?: boolean;
    selectNodesOnDrag?: boolean;
    panOnDrag?: boolean | number[];
    panOnScroll?: boolean;
    panOnScrollSpeed?: number;
    panOnScrollMode?: 'free' | 'vertical' | 'horizontal';
    zoomOnScroll?: boolean;
    zoomOnPinch?: boolean;
    zoomOnDoubleClick?: boolean;
    preventScrolling?: boolean;
    connectionMode?: 'strict' | 'loose';
    connectionRadius?: number;
    autoPanOnConnect?: boolean;
    autoPanOnNodeDrag?: boolean;
    autoPanSpeed?: number;
    nodeDragThreshold?: number;
    noDragClassName?: string;
    noWheelClassName?: string;
    noPanClassName?: string;
    translateExtent?: [[number, number], [number, number]];
    nodeExtent?: [[number, number], [number, number]];
    elevateNodesOnSelect?: boolean;
    elevateEdgesOnSelect?: boolean;
    deleteKeyCode?: string | string[] | null;
    selectionKeyCode?: string | string[] | null;
    multiSelectionKeyCode?: string | string[] | null;
    zoomActivationKeyCode?: string | string[] | null;
    panActivationKeyCode?: string | string[] | null;
    proOptions?: { hideAttribution?: boolean };
    style?: CSSProperties;
    className?: string;
    children?: ReactNode;
  }

  export const ReactFlow: ComponentType<ReactFlowProps>;
  export const ReactFlowProvider: ComponentType<{ children: ReactNode }>;
  
  export const Background: ComponentType<{
    id?: string;
    color?: string;
    gap?: number | [number, number];
    size?: number;
    offset?: number;
    lineWidth?: number;
    variant?: 'dots' | 'lines' | 'cross';
    style?: CSSProperties;
    className?: string;
  }>;
  
  export const Controls: ComponentType<{
    showZoom?: boolean;
    showFitView?: boolean;
    showInteractive?: boolean;
    fitViewOptions?: FitViewOptions;
    onZoomIn?: () => void;
    onZoomOut?: () => void;
    onFitView?: () => void;
    onInteractiveChange?: (interactiveStatus: boolean) => void;
    style?: CSSProperties;
    className?: string;
    position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
    orientation?: 'horizontal' | 'vertical';
  }>;
  
  export const MiniMap: ComponentType<{
    nodeColor?: string | ((node: Node) => string);
    nodeStrokeColor?: string | ((node: Node) => string);
    nodeStrokeWidth?: number;
    nodeBorderRadius?: number;
    nodeClassName?: string | ((node: Node) => string);
    maskColor?: string;
    maskStrokeColor?: string;
    maskStrokeWidth?: number;
    style?: CSSProperties;
    className?: string;
    position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
    pannable?: boolean;
    zoomable?: boolean;
    inversePan?: boolean;
    zoomStep?: number;
    offsetScale?: number;
  }>;
  
  export const Panel: ComponentType<{
    position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'top-center' | 'bottom-center';
    style?: CSSProperties;
    className?: string;
    children?: ReactNode;
  }>;
  
  export const MarkerType: {
    Arrow: 'arrow';
    ArrowClosed: 'arrowclosed';
  };
}

declare module '@xyflow/react/dist/style.css';
