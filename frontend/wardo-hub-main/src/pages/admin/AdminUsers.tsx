import { useState, useEffect } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Search, MoreHorizontal, Eye, Edit2, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { apiUrl, getAuthHeader } from '@/lib/api';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useToast } from '@/hooks/use-toast';
import AdminSidebar from '@/components/layout/AdminSidebar';
import { clearAuthState, getAuthState } from '@/lib/auth';

type AdminUser = {
  id: string;
  name: string;
  email: string;
  role: string;
  bio?: string;
  status: 'Active';
  joined: string;
  avatar: string;
};

const AdminUsers = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const [viewOpen, setViewOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editForm, setEditForm] = useState({
    name: '',
    email: '',
    role: 'user',
    bio: '',
  });
  const auth = getAuthState();
  const isAdmin = auth.isAdmin;

  useEffect(() => {
    if (isAdmin) {
      fetchUsers();
    }
  }, [isAdmin]);

  const handleUnauthorized = () => {
    clearAuthState();
    toast({
      variant: 'destructive',
      title: 'Session Expired',
      description: 'Please sign in again.',
    });
    navigate('/auth', { replace: true });
  };

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const response = await fetch(apiUrl('/admin/users?limit=6'), {
        headers: {
          ...getAuthHeader(),
        },
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          handleUnauthorized();
          return;
        }
        const message = data?.message || 'Failed to load users.';
        toast({
          variant: 'destructive',
          title: 'Fetch Failed',
          description: message,
        });
        return;
      }

      const mapped: AdminUser[] = (data.users || []).map((u: { _id: string; name: string; email: string; role?: string; bio?: string; createdAt?: string }) => {
        const initials = (u.name || u.email || 'U')
          .split(' ')
          .map((part) => part[0])
          .join('')
          .slice(0, 2)
          .toUpperCase();

        return {
          id: u._id,
          name: u.name || 'Unnamed User',
          email: u.email || 'unknown@example.com',
          role: u.role || 'user',
          bio: u.bio || '',
          status: 'Active',
          joined: u.createdAt || new Date().toISOString(),
          avatar: initials || 'U',
        };
      });

      setUsers(mapped);
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Fetch Failed',
        description: 'Network error. Please try again.',
      });
    } finally {
      setLoading(false);
    }
  };

  const filteredUsers = users.filter((u) => {
    const matchesSearch =
      u.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.email.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || u.status.toLowerCase() === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const fetchUserDetails = async (userId: string) => {
    setDetailLoading(true);
    try {
      const response = await fetch(apiUrl(`/admin/users/${userId}`), {
        headers: {
          ...getAuthHeader(),
        },
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          handleUnauthorized();
          return null;
        }
        const message = data?.message || 'Failed to load user.';
        toast({
          variant: 'destructive',
          title: 'Fetch Failed',
          description: message,
        });
        return null;
      }

      const u = data.user;
      const initials = (u.name || u.email || 'U')
        .split(' ')
        .map((part: string) => part[0])
        .join('')
        .slice(0, 2)
        .toUpperCase();

      return {
        id: u._id,
        name: u.name || 'Unnamed User',
        email: u.email || 'unknown@example.com',
        role: u.role || 'user',
        bio: u.bio || '',
        status: 'Active',
        joined: u.createdAt || new Date().toISOString(),
        avatar: initials || 'U',
      } as AdminUser;
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Fetch Failed',
        description: 'Network error. Please try again.',
      });
      return null;
    } finally {
      setDetailLoading(false);
    }
  };

  const handleView = async (userId: string) => {
    const userData = await fetchUserDetails(userId);
    if (!userData) return;
    setSelectedUser(userData);
    setViewOpen(true);
  };

  const handleEdit = async (userId: string) => {
    const userData = await fetchUserDetails(userId);
    if (!userData) return;
    setSelectedUser(userData);
    setEditForm({
      name: userData.name,
      email: userData.email,
      role: userData.role || 'user',
      bio: userData.bio || '',
    });
    setEditOpen(true);
  };

  const handleSaveEdit = async () => {
    if (!selectedUser) return;
    setSaving(true);
    try {
      const response = await fetch(apiUrl(`/admin/users/${selectedUser.id}`), {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeader(),
        },
        body: JSON.stringify({
          name: editForm.name,
          email: editForm.email,
          role: editForm.role,
          bio: editForm.bio,
        }),
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          handleUnauthorized();
          return;
        }
        const message = data?.message || 'Failed to update user.';
        toast({
          variant: 'destructive',
          title: 'Update Failed',
          description: message,
        });
        return;
      }

      toast({
        title: 'User Updated',
        description: 'User details were updated successfully.',
      });
      setEditOpen(false);
      setSelectedUser(null);
      fetchUsers();
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Update Failed',
        description: 'Network error. Please try again.',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = (userId: string) => {
    setPendingDeleteId(userId);
    setDeleteOpen(true);
  };

  const confirmDelete = async () => {
    if (!pendingDeleteId) return;
    setDeleting(true);
    try {
      const response = await fetch(apiUrl(`/admin/users/${pendingDeleteId}`), {
        method: 'DELETE',
        headers: {
          ...getAuthHeader(),
        },
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          handleUnauthorized();
          return;
        }
        const message = data?.message || 'Failed to delete user.';
        toast({
          variant: 'destructive',
          title: 'Delete Failed',
          description: message,
        });
        return;
      }

      toast({
        title: 'User Deleted',
        description: 'User account has been removed.',
      });
      setDeleteOpen(false);
      setPendingDeleteId(null);
      fetchUsers();
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Delete Failed',
        description: 'Network error. Please try again.',
      });
    } finally {
      setDeleting(false);
    }
  };

  if (!isAdmin) {
    return <Navigate to="/auth" replace />;
  }

  return (
    <div className="min-h-screen bg-background">
      <AdminSidebar />

      <main className="p-6 lg:p-8 lg:ml-64">
        <div className="mb-8">
          <h1 className="text-3xl font-playfair font-bold">Users</h1>
          <p className="text-muted-foreground mt-1">Manage and view all registered users.</p>
        </div>

        <Card className="border-none shadow-md">
          <CardHeader>
            <div className="flex flex-col sm:flex-row gap-4 justify-between">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search by name or email..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-40">
                  <SelectValue placeholder="Filter by status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-12">
                <p className="text-muted-foreground">Loading users...</p>
              </div>
            ) : filteredUsers.length === 0 ? (
              <div className="text-center py-12">
                <p className="text-muted-foreground">No users found.</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>User</TableHead>
                      <TableHead>Role</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Joined</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredUsers.map((u) => (
                    <TableRow key={u.id}>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <div className="h-10 w-10 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-medium">
                            {u.avatar}
                          </div>
                          <div>
                            <p className="font-medium">{u.name}</p>
                            <p className="text-sm text-muted-foreground">{u.email}</p>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="capitalize">{u.role}</TableCell>
                      <TableCell>
                        <Badge
                          variant={u.status === 'Active' ? 'default' : 'secondary'}
                          className={
                            u.status === 'Active'
                              ? 'bg-primary/10 text-primary hover:bg-primary/20'
                              : ''
                          }
                        >
                          {u.status}
                        </Badge>
                      </TableCell>
                      <TableCell>{new Date(u.joined).toLocaleDateString()}</TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => handleView(u.id)}>
                              <Eye className="h-4 w-4 mr-2" />
                              View
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => handleEdit(u.id)}>
                              <Edit2 className="h-4 w-4 mr-2" />
                              Edit
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => handleDelete(u.id)}
                              className="text-destructive"
                            >
                              <Trash2 className="h-4 w-4 mr-2" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </main>

      <Dialog open={viewOpen} onOpenChange={setViewOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>User Details</DialogTitle>
          </DialogHeader>
          {detailLoading || !selectedUser ? (
            <div className="py-6 text-center text-muted-foreground">Loading user...</div>
          ) : (
            <div className="space-y-4">
              <div>
                <Label className="text-muted-foreground">Name</Label>
                <p className="font-medium">{selectedUser.name}</p>
              </div>
              <div>
                <Label className="text-muted-foreground">Email</Label>
                <p className="font-medium">{selectedUser.email}</p>
              </div>
              <div>
                <Label className="text-muted-foreground">Role</Label>
                <p className="font-medium capitalize">{selectedUser.role}</p>
              </div>
              <div>
                <Label className="text-muted-foreground">Bio</Label>
                <p className="text-sm text-muted-foreground">{selectedUser.bio || 'No bio provided.'}</p>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit User</DialogTitle>
          </DialogHeader>
          {detailLoading ? (
            <div className="py-6 text-center text-muted-foreground">Loading user...</div>
          ) : (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="edit-name">Name</Label>
                <Input
                  id="edit-name"
                  value={editForm.name}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, name: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-email">Email</Label>
                <Input
                  id="edit-email"
                  type="email"
                  value={editForm.email}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, email: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label>Role</Label>
                <Select
                  value={editForm.role}
                  onValueChange={(value) => setEditForm((prev) => ({ ...prev, role: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select role" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="user">User</SelectItem>
                    <SelectItem value="admin">Admin</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-bio">Bio</Label>
                <Textarea
                  id="edit-bio"
                  rows={3}
                  value={editForm.bio}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, bio: e.target.value }))}
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveEdit} disabled={saving}>
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete user?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete the user account.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setPendingDeleteId(null)}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} disabled={deleting}>
              {deleting ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};

export default AdminUsers;
