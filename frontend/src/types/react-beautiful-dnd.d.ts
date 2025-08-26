/**
 * react-beautiful-dnd 类型声明
 */
declare module 'react-beautiful-dnd' {
  import { ComponentType, ReactNode } from 'react';
  
  export interface DraggableLocation {
    droppableId: string;
    index: number;
  }
  
  export interface DragResult {
    destination?: DraggableLocation;
    source: DraggableLocation;
    draggableId: string;
    mode: 'FLUID' | 'SNAP';
    combine?: any;
    reason: 'DROP' | 'CANCEL';
  }
  
  export type DropResult = DragResult & {
    reason: 'DROP';
  };
  
  export interface ResponderProvided {
    announce: (message: string) => void;
  }
  
  export interface DroppableProvided {
    innerRef: (element: HTMLElement | null) => void;
    droppableProps: {
      'data-rbd-droppable-id': string;
      'data-rbd-droppable-context-id': string;
    };
    placeholder?: ReactNode;
  }
  
  export interface DroppableStateSnapshot {
    isDraggingOver: boolean;
    draggingOverWith?: string;
    draggingFromThisWith?: string;
    isUsingPlaceholder: boolean;
  }
  
  export interface DraggableProvided {
    draggableProps: any;
    dragHandleProps: any | null;
    innerRef: (element: HTMLElement | null) => void;
  }
  
  export interface DraggableStateSnapshot {
    isDragging: boolean;
    isDropAnimating: boolean;
    isClone: boolean;
    dropAnimation: any | null;
    draggingOver: string | null;
    combineWith: string | null;
    combineTargetFor: string | null;
    mode: string | null;
  }
  
  export const DragDropContext: ComponentType<any>;
  export const Droppable: ComponentType<any>;
  export const Draggable: ComponentType<any>;
} 