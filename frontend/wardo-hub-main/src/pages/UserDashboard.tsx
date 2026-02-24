import { Link } from 'react-router-dom';
import { Sparkles, User, LayoutGrid, Shirt } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import Navbar from '@/components/layout/Navbar';
import UserSidebar from '@/components/layout/UserSidebar';

const UserDashboard = () => {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <UserSidebar />

      <main className="p-6 lg:p-10">
        <div className="max-w-4xl space-y-8">
          <div className="space-y-2">
            <h1 className="text-4xl font-playfair font-bold">Your Dashboard</h1>
            <p className="text-muted-foreground">
              Quick access to your style tools and profile.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <Card className="border-0 shadow-lg">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <LayoutGrid className="h-5 w-5 text-primary" />
                  Style Studio
                </CardTitle>
                <CardDescription>Glow Up, Mix & Match, and your wardrobe in one place.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Sparkles className="h-4 w-4" />
                  Glow Up
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Shirt className="h-4 w-4" />
                  Mix & Match
                </div>
                <Button asChild className="w-full">
                  <Link to="/style-studio">Go to Style Studio</Link>
                </Button>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-lg">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <User className="h-5 w-5 text-primary" />
                  Profile
                </CardTitle>
                <CardDescription>Manage your info, profile photo, and preferences.</CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild variant="outline" className="w-full">
                  <Link to="/profile">Go to Profile</Link>
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
};

export default UserDashboard;
