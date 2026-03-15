declare module "react-grid-layout" {
  import * as React from "react";

  export interface Layout {
    i: string;
    x: number;
    y: number;
    w: number;
    h: number;
    minW?: number;
    maxW?: number;
    minH?: number;
    maxH?: number;
    static?: boolean;
    isDraggable?: boolean;
    isResizable?: boolean;
    moved?: boolean;
  }

  export interface Layouts {
    [breakpoint: string]: Layout[];
  }

  type ResizeHandle = "s" | "w" | "e" | "n" | "sw" | "nw" | "se" | "ne";

  export interface DragConfig {
    enabled?: boolean;
    handle?: string;
    cancel?: string;
    bounded?: boolean;
    threshold?: number;
  }

  export interface ResizeConfig {
    enabled?: boolean;
    handles?: ResizeHandle[];
    handleComponent?: React.ReactNode | ((axis: ResizeHandle, ref: React.Ref<HTMLElement>) => React.ReactNode);
  }

  interface CoreProps {
    className?: string;
    style?: React.CSSProperties;
    width?: number;
    autoSize?: boolean;
    compactType?: "vertical" | "horizontal" | null;
    margin?: [number, number] | { [P: string]: [number, number] };
    containerPadding?: [number, number] | { [P: string]: [number, number] } | null;
    rowHeight?: number;
    useCSSTransforms?: boolean;
    children?: React.ReactNode;
    dragConfig?: DragConfig;
    resizeConfig?: ResizeConfig;
    onDragStart?: (...args: unknown[]) => void;
    onDrag?: (...args: unknown[]) => void;
    onDragStop?: (...args: unknown[]) => void;
    onResizeStart?: (...args: unknown[]) => void;
    onResize?: (...args: unknown[]) => void;
    onResizeStop?: (...args: unknown[]) => void;
  }

  export interface ResponsiveGridLayoutProps extends CoreProps {
    breakpoints?: { [P: string]: number };
    cols?: { [P: string]: number };
    layouts?: Layouts;
    onBreakpointChange?(newBreakpoint: string, newCols: number): void;
    onLayoutChange?(currentLayout: Layout[], allLayouts: Layouts): void;
    onWidthChange?(containerWidth: number, margin: [number, number], cols: number, containerPadding: [number, number]): void;
  }

  export const ResponsiveGridLayout: React.ComponentType<ResponsiveGridLayoutProps>;
  export const Responsive: React.ComponentType<ResponsiveGridLayoutProps>;

  export interface GridLayoutProps extends CoreProps {
    cols?: number;
    layout?: Layout[];
    onLayoutChange?(layout: Layout[]): void;
  }

  export const GridLayout: React.ComponentType<GridLayoutProps>;

  export function useContainerWidth(options?: {
    measureBeforeMount?: boolean;
    initialWidth?: number;
  }): {
    width: number;
    mounted: boolean;
    containerRef: React.RefObject<HTMLDivElement | null>;
    measureWidth: () => void;
  };

  const ReactGridLayout: React.ComponentType<GridLayoutProps>;
  export default ReactGridLayout;
}
