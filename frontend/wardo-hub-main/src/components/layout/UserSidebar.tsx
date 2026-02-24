import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { LayoutGrid, User, Sparkles, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';

type UserSidebarProps = {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

const UserSidebar = ({ open, onOpenChange }: UserSidebarProps) => {
  const location = useLocation();
  const navigate = useNavigate();
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = typeof open === 'boolean';
  const isOpen = isControlled ? open : internalOpen;
  const setIsOpen = (next: boolean) => {
    if (isControlled) {
      onOpenChange?.(next);
    } else {
      setInternalOpen(next);
    }
  };

  const handleSignOut = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    localStorage.removeItem('email');
    localStorage.removeItem('profile');
    navigate('/auth');
  };

  const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: LayoutGrid },
    { path: '/profile', label: 'Profile', icon: User },
    { path: '/style-studio', label: 'Style Studio', icon: Sparkles },
  ];

  return (
    <>
      {isOpen && (
        <div
          className="fixed left-0 right-0 bottom-0 top-16 bg-black/40 z-40"
          onClick={() => setIsOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed right-0 top-16 z-50 h-[calc(100vh-4rem)] w-72 bg-card border-l border-border shadow-xl transition-transform duration-300 ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="p-6 border-b border-border">
          <Link to="/dashboard" className="flex items-center space-x-2" onClick={() => setIsOpen(false)}>
            <span className="text-2xl font-playfair font-bold text-accent">Wardo</span>
          </Link>
          <p className="text-xs text-muted-foreground mt-1">User Dashboard</p>
        </div>

        <nav className="flex-1 p-4 space-y-2">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setIsOpen(false)}
                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                }`}
              >
                <item.icon className="h-5 w-5" />
                <span className="font-medium">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-border">
          <Button
            variant="ghost"
            className="w-full justify-start text-muted-foreground hover:text-foreground"
            onClick={handleSignOut}
          >
            <LogOut className="h-4 w-4 mr-2" />
            Sign Out
          </Button>
        </div>
      </aside>
    </>
  );
};

export default UserSidebar;
