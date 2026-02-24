import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Upload, Trash2, Plus } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { useToast } from '@/hooks/use-toast';
import { apiUrl, getAuthHeader } from '@/lib/api';
import Navbar from '@/components/layout/Navbar';
import Footer from '@/components/layout/Footer';

type WardrobeItem = {
  _id: string;
  imagePath: string;
  details?: {
    name?: string;
    category?: string;
    description?: string;
  };
};

const MyWardrobe = () => {
  const { toast } = useToast();
  const [items, setItems] = useState<WardrobeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState('');
  const [category, setCategory] = useState('top');
  const [description, setDescription] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  useEffect(() => {
    fetchWardrobe();
  }, []);

  const fetchWardrobe = async () => {
    setLoading(true);
    try {
      const response = await fetch(apiUrl('/wardrobe'), {
        headers: {
          ...getAuthHeader(),
        },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message = data?.message || 'Failed to load wardrobe.';
        toast({
          variant: 'destructive',
          title: 'Fetch Failed',
          description: message,
        });
        return;
      }
      setItems(data.items || []);
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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setFile(selected);
    const reader = new FileReader();
    reader.onload = () => setPreview(reader.result as string);
    reader.readAsDataURL(selected);
  };

  const handleUpload = async () => {
    if (!file) {
      toast({
        variant: 'destructive',
        title: 'Missing Image',
        description: 'Please select an image to upload.',
      });
      return;
    }

    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('image', file);
      formData.append('name', name || 'Untitled Item');
      formData.append('category', category);
      if (description.trim()) {
        formData.append('description', description.trim());
      }

      const response = await fetch(apiUrl('/wardrobe'), {
        method: 'POST',
        headers: {
          ...getAuthHeader(),
        },
        body: formData,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message = data?.message || 'Failed to upload item.';
        toast({
          variant: 'destructive',
          title: 'Upload Failed',
          description: message,
        });
        return;
      }

      toast({
        title: 'Item Added',
        description: 'Your wardrobe item was uploaded.',
      });
      setName('');
      setCategory('top');
      setDescription('');
      setFile(null);
      setPreview(null);
      setDialogOpen(false);
      fetchWardrobe();
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Upload Failed',
        description: 'Network error. Please try again.',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const response = await fetch(apiUrl(`/wardrobe/${id}`), {
        method: 'DELETE',
        headers: {
          ...getAuthHeader(),
        },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message = data?.message || 'Failed to delete item.';
        toast({
          variant: 'destructive',
          title: 'Delete Failed',
          description: message,
        });
        return;
      }
      toast({
        title: 'Item Deleted',
        description: 'Your wardrobe item was removed.',
      });
      setItems((prev) => prev.filter((item) => item._id !== id));
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Delete Failed',
        description: 'Network error. Please try again.',
      });
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Navbar />

      <main className="container mx-auto px-4 py-8 flex-1">
        <Link
          to="/style-studio"
          className="inline-flex items-center text-muted-foreground hover:text-foreground mb-6"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Style Studio
        </Link>

        <div className="max-w-6xl mx-auto space-y-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-4xl font-playfair font-bold mb-2">My Wardrobe</h1>
              <p className="text-muted-foreground">
                Your saved outfits and style favorites.
              </p>
            </div>
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button className="gap-2">
                  <Plus className="h-4 w-4" />
                  Add Item
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-2xl">
                <DialogHeader>
                  <DialogTitle>Add New Item</DialogTitle>
                </DialogHeader>
                <div className="grid gap-6 md:grid-cols-[1fr,1fr]">
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="item-name">Item Name</Label>
                      <Input
                        id="item-name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="e.g. Summer Dress"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Category</Label>
                      <Select value={category} onValueChange={setCategory}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select category" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="top">Top</SelectItem>
                          <SelectItem value="bottom">Bottom</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="item-desc">Description (optional)</Label>
                      <Textarea
                        id="item-desc"
                        rows={3}
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="Add a short note about this item..."
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Upload Image</Label>
                      <div className="flex items-center gap-3">
                        <label className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-border cursor-pointer hover:bg-secondary/50">
                          <Upload className="h-4 w-4" />
                          Choose File
                          <input type="file" accept="image/*" className="hidden" onChange={handleFileChange} />
                        </label>
                        <span className="text-sm text-muted-foreground">
                          {file ? file.name : 'No file selected'}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="bg-secondary/30 rounded-xl p-4 flex items-center justify-center">
                    {preview ? (
                      <img src={preview} alt="Preview" className="max-h-56 rounded-lg object-cover" />
                    ) : (
                      <p className="text-sm text-muted-foreground">Image preview will appear here.</p>
                    )}
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setDialogOpen(false)}>
                    Cancel
                  </Button>
                  <Button onClick={handleUpload} disabled={saving}>
                    {saving ? 'Uploading...' : 'Add to Wardrobe'}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>

          {loading ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground">Loading wardrobe...</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
              {items.map((item) => (
                <Card
                  key={item._id}
                  className="overflow-hidden border-none shadow-lg hover:shadow-xl transition-shadow cursor-pointer group"
                >
                  <CardContent className="p-0">
                    <div className="relative overflow-hidden">
                      <img
                        src={apiUrl(item.imagePath)}
                        alt={item.details?.name || 'Wardrobe item'}
                        className="w-full h-64 object-cover transition-transform duration-300 group-hover:scale-105"
                      />
                      <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                      <div className="absolute bottom-0 left-0 right-0 p-4 text-white transform translate-y-full group-hover:translate-y-0 transition-transform">
                        <div className="flex items-start justify-between gap-3">
                          <div className="space-y-1">
                            <p className="font-medium">{item.details?.name || 'Untitled Item'}</p>
                            <div className="text-xs uppercase tracking-wide text-white/80">
                              {item.details?.category || 'Uncategorized'}
                            </div>
                            {item.details?.description && (
                              <p className="text-xs text-white/80">
                                {item.details.description}
                              </p>
                            )}
                          </div>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-white hover:text-white"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              handleDelete(item._id);
                            }}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {!loading && items.length === 0 && (
            <div className="text-center py-16">
              <p className="text-muted-foreground text-lg mb-4">
                Your wardrobe is empty.
              </p>
              <p className="text-sm text-muted-foreground">
                Start adding outfits from Glow Up and Mix & Match features.
              </p>
            </div>
          )}
        </div>
      </main>

      <Footer />
    </div>
  );
};

export default MyWardrobe;
