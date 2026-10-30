export type AdminRole = 'ADMIN'|'DEVELOPER'|'ARCHITECT'|'VIEWER';
export interface AdminUser { id:string; email:string; full_name:string; role:AdminRole; is_active:boolean; }
