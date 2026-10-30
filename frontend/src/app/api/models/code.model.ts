export interface FileContent {
  path: string;
  language: string;
  content: string;
  lines: number;
  size: number;
  isMock: boolean;
}

export interface FileTreeNode {
  path: string;
  name: string;
  type: 'file' | 'directory';
  language?: string;
  children?: FileTreeNode[];
  expanded?: boolean;
}
