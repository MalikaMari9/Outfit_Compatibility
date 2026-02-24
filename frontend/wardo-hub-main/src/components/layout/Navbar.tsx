import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Bell, Menu, X, MoreHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import NotificationsDropdown from './NotificationsDropdown';
import UserSidebar from './UserSidebar';

const Navbar = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const navigate = useNavigate();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const storedRole = typeof window !== 'undefined' ? localStorage.getItem('role') : null;
  const storedToken = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const isAdmin = storedRole === 'admin';
  const isAuthed = Boolean(storedToken || storedRole);

  return (
    <nav className="sticky top-0 z-50 bg-card/95 backdrop-blur-sm border-b border-border">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center space-x-2">
            <span className="text-2xl font-playfair font-bold text-accent">Wardo</span>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center space-x-8">
            <Link
              to="/"
              className="text-muted-foreground hover:text-foreground transition-colors font-medium"
            >
              Home
            </Link>
            {isAuthed && !isAdmin && (
              <Link
                to="/style-studio"
                className="text-muted-foreground hover:text-foreground transition-colors font-medium"
              >
                Style Studio
              </Link>
            )}
            <Link
              to="/about"
              className="text-muted-foreground hover:text-foreground transition-colors font-medium"
            >
              About Us
            </Link>
          </div>

          {/* Right Side - Auth & Actions */}
          <div className="hidden md:flex items-center space-x-4">
            {isAuthed ? (
              <>
                <NotificationsDropdown />
                {!isAdmin && (
                  <UserSidebar open={userMenuOpen} onOpenChange={setUserMenuOpen} />
                )}
                {!isAdmin && (
                  <Button
                    variant="outline"
                    size="icon"
                    className="rounded-full"
                    onClick={() => setUserMenuOpen((prev) => !prev)}
                    aria-label={userMenuOpen ? 'Close menu' : 'Open menu'}
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                )}
                
              </>
            ) : (
              <>
                <Button
                  variant="ghost"
                  onClick={() => navigate('/auth')}
                  className="text-muted-foreground hover:text-foreground"
                >
                  Sign In
                </Button>
                <Button
                  onClick={() => navigate('/auth?tab=signup')}
                  className="bg-primary text-primary-foreground hover:bg-primary/90"
                >
                  Sign Up
                </Button>
              </>
            )}
          </div>

          {/* Mobile Menu Button */}
          <button
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            className="md:hidden text-foreground"
          >
            {isMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>

        {/* Mobile Menu */}
        {isMenuOpen && (
          <div className="md:hidden py-4 border-t border-border animate-fade-in">
            <div className="flex flex-col space-y-4">
              <Link
                to="/"
                className="text-foreground hover:text-primary transition-colors font-medium"
                onClick={() => setIsMenuOpen(false)}
              >
                Home
              </Link>
              {isAuthed && !isAdmin && (
                <Link
                  to="/style-studio"
                  className="text-foreground hover:text-primary transition-colors font-medium"
                  onClick={() => setIsMenuOpen(false)}
                >
                  Style Studio
                </Link>
              )}
              <Link
                to="/about"
                className="text-foreground hover:text-primary transition-colors font-medium"
                onClick={() => setIsMenuOpen(false)}
              >
                About Us
              </Link>
              {isAuthed ? (
                <>
                  <Link
                    to="/profile"
                    className="text-foreground hover:text-primary transition-colors font-medium"
                    onClick={() => setIsMenuOpen(false)}
                  >
                    Profile
                  </Link>
                  {!isAdmin && (
                    <Button
                      variant="ghost"
                      className="justify-start px-0 text-foreground hover:text-primary"
                      onClick={() => {
                        setUserMenuOpen(true);
                        setIsMenuOpen(false);
                      }}
                    >
                      <MoreHorizontal className="h-4 w-4 mr-2" />
                      Menu
                    </Button>
                  )}
                </>
              ) : (
                <div className="flex flex-col space-y-2 pt-4 border-t border-border">
                  <Button
                    variant="ghost"
                    onClick={() => {
                      navigate('/auth');
                      setIsMenuOpen(false);
                    }}
                  >
                    Sign In
                  </Button>
                  <Button
                    onClick={() => {
                      navigate('/auth?tab=signup');
                      setIsMenuOpen(false);
                    }}
                  >
                    Sign Up
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </nav>
  );
};

export default Navbar;
