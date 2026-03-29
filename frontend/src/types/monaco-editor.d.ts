/**
 * Monaco Editor type declarations
 * This file provides type declarations for @monaco-editor/react package
 * until npm install is run in the deployment environment.
 */

declare module '@monaco-editor/react' {
  import * as React from 'react';
  import type { editor } from 'monaco-editor';

  export interface EditorProps {
    height?: string | number;
    width?: string | number;
    language?: string;
    value?: string;
    defaultValue?: string;
    defaultLanguage?: string;
    theme?: string;
    options?: editor.IStandaloneEditorConstructionOptions;
    onChange?: (value: string | undefined) => void;
    onMount?: OnMount;
    beforeMount?: BeforeMount;
    onValidate?: (markers: editor.IMarker[]) => void;
    className?: string;
    wrapperProps?: object;
    loading?: React.ReactNode;
    line?: number;
    path?: string;
    saveViewState?: boolean;
    keepCurrentModel?: boolean;
  }

  export type OnMount = (
    editor: editor.IStandaloneCodeEditor,
    monaco: Monaco
  ) => void;

  export type BeforeMount = (monaco: Monaco) => void;

  export interface Monaco {
    editor: typeof editor;
    languages: any;
    KeyMod: any;
    KeyCode: any;
  }

  const Editor: React.FC<EditorProps>;
  export default Editor;
}

declare module 'monaco-editor' {
  export namespace editor {
    interface IStandaloneCodeEditor {
      getModel(): ITextModel | null;
      getValue(): string;
      setValue(value: string): void;
      focus(): void;
      addCommand(keybinding: number, handler: () => void): void | null;
    }

    interface ITextModel {
      getWordUntilPosition(position: IPosition): IWordAtPosition;
    }

    interface IPosition {
      lineNumber: number;
      column: number;
    }

    interface IWordAtPosition {
      word: string;
      startColumn: number;
      endColumn: number;
    }

    interface IMarker {
      message: string;
      severity: number;
      startLineNumber: number;
      startColumn: number;
      endLineNumber: number;
      endColumn: number;
    }

    interface IStandaloneEditorConstructionOptions {
      minimap?: { enabled?: boolean };
      lineNumbers?: 'on' | 'off' | 'relative' | 'interval';
      fontSize?: number;
      fontFamily?: string;
      tabSize?: number;
      wordWrap?: 'on' | 'off' | 'wordWrapColumn' | 'bounded';
      automaticLayout?: boolean;
      scrollBeyondLastLine?: boolean;
      quickSuggestions?: boolean;
      suggestOnTriggerCharacters?: boolean;
      readOnly?: boolean;
      renderLineHighlight?: 'all' | 'line' | 'none' | 'gutter';
      cursorBlinking?: 'blink' | 'smooth' | 'phase' | 'expand' | 'solid';
      smoothScrolling?: boolean;
      padding?: { top?: number; bottom?: number };
      scrollbar?: {
        verticalScrollbarSize?: number;
        horizontalScrollbarSize?: number;
      };
    }

    function setModelLanguage(model: ITextModel, language: string): void;
  }
}

